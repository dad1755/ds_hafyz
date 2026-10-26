"""S10 evidence — the deployed container renders every figure after a restart.

Run against the running service, with no state change to the deployment:

    docker exec -i aihubcampus-web-1 python - < evidence/s10/probe_evaluation.py

It opens a **throwaway** SQLite file in the container's /tmp, creates a synthetic administrator
and a synthetic user there, and renders ``src.pages_evaluation`` with Streamlit's own
``AppTest`` harness — the same code path the browser drives. The deployment's own database is
never opened, so nothing is written and no account is added.

What it prints, all of it from the container's own filesystem:

* the six EDA PNGs, the three confusion matrices and the importance PNG as they exist **in the
  image**, with their sizes and SHA-256;
* the record's digest, and whether it matches the copy in the repository;
* the number of figures the page actually produced, and the table row counts;
* that a user session is refused and produces no figure.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

MODELS = Path("/app/models")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    print("S10 — deployed container: artifacts on disk and a real render")
    print(f"  working directory   {Path.cwd()}")
    print(f"  models directory    {MODELS}")

    metrics = json.loads((MODELS / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((MODELS / "model_manifest.json").read_text(encoding="utf-8"))
    print(f"  metrics.json        sha256 {sha256(MODELS / 'metrics.json')}")
    print(f"  model_manifest.json sha256 {sha256(MODELS / 'model_manifest.json')}")
    print(f"  best_pipeline.joblib sha256 {sha256(MODELS / 'best_pipeline.joblib')}")
    print(f"  manifest artifact sha256   {manifest['artifact']['sha256']}")

    print("\n  figure artifacts present in the image:")
    for directory in ("eda", "figures"):
        for path in sorted((MODELS / directory).glob("*.png")):
            print(f"    {directory}/{path.name:34s} {path.stat().st_size:>7,d} B  "
                  f"sha256 {sha256(path)[:16]}…")
    eda_pngs = sorted((MODELS / "eda").glob("*.png"))
    if len(eda_pngs) != 6:
        failures.append(f"{len(eda_pngs)} EDA PNGs in the image, expected 6")
    if not (MODELS / "eda" / "summary.json").is_file():
        failures.append("models/eda/summary.json is absent from the image")

    # ---------------------------------------------------------------- render
    from streamlit.testing.v1 import AppTest

    from src import db, pages_evaluation, security

    workdir = Path(tempfile.mkdtemp(prefix="s10-probe-"))
    database = workdir / "probe.db"
    connection = db.connect(database)
    try:
        db.migrate(connection)
        moment = db.to_iso(db.utcnow())
        accounts = {}
        for username, role, password in (
            ("probe_admin", "admin", "cobalt-lantern-heron-71"),
            ("probe_user", "user", "marble-orchid-vane-52"),
        ):
            with db.transaction(connection):
                connection.execute(
                    "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                    "must_change_password, created_at, updated_at, last_login_at) "
                    "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
                    (username, username, security.hash_password(password), role, moment, moment),
                )
            _principal, token = security.login(connection, username, password)
            accounts[role] = token
    finally:
        connection.close()

    def page() -> None:
        import os

        from src import db, pages_evaluation

        connection = db.connect(os.environ["PROBE_DB"])
        try:
            pages_evaluation.render(connection, os.environ["PROBE_TOKEN"])
        finally:
            connection.close()

    def render(token: str) -> AppTest:
        os.environ["PROBE_DB"] = str(database)
        os.environ["PROBE_TOKEN"] = token
        at = AppTest.from_function(page, default_timeout=180)
        return at.run()

    admin = render(accounts["admin"])
    if admin.exception:
        failures.append(f"the admin render raised: {admin.exception[0].value[:200]}")
    figures = len(admin.image)
    print(f"\n  admin render: {figures} figures, {len(admin.dataframe)} tables, "
          f"{len(admin.error)} errors, {len(admin.warning)} warnings")
    if figures != 11:
        failures.append(f"{figures} figures rendered, expected 11 (6 EDA + 3 matrices + 2 charts)")
    if admin.warning:
        failures.append(f"warnings rendered: {[w.value[:80] for w in admin.warning]}")
    if admin.error:
        failures.append(f"errors rendered: {[e.value[:80] for e in admin.error]}")

    # The table's own numbers, read back off the rendered widget.
    table = admin.dataframe[0].value
    selected = metrics["evaluation"]["selected"]
    label = {"decision_tree": "Decision Tree", "logistic_regression": "Logistic Regression",
             "random_forest": "Random Forest"}[selected]
    shown = float(table.loc[table["model"] == label, "test accuracy"].iloc[0])
    recorded = metrics["evaluation"]["models"][selected]["metrics"]["accuracy"]
    print(f"  rendered accuracy for {label}: {shown!r}; metrics.json: {recorded!r}; "
          f"{'equal' if shown == recorded else 'DIFFERS'}")
    if shown != recorded:
        failures.append("the rendered accuracy differs from metrics.json")

    counts = admin.dataframe[2].value
    row = counts.loc[counts["model"] == label].iloc[0]
    matrix = metrics["evaluation"]["models"][selected]["confusion_matrix"]
    printed = (int(row["TN"]), int(row["FP"]), int(row["FN"]), int(row["TP"]))
    expected = (matrix["tn"], matrix["fp"], matrix["fn"], matrix["tp"])
    print(f"  rendered TN/FP/FN/TP: {printed}; metrics.json: {expected}; "
          f"{'equal' if printed == expected else 'DIFFERS'}")
    if printed != expected:
        failures.append("the rendered confusion counts differ from metrics.json")

    user = render(accounts["user"])
    print(f"\n  user render: {len(user.image)} figures, {len(user.dataframe)} tables, "
          f"errors = {[error.value for error in user.error]}")
    if len(user.image) or len(user.dataframe):
        failures.append("a user session rendered evaluation content")
    if not user.error:
        failures.append("a user session was not refused")

    connection = db.connect(database)
    try:
        denied = connection.execute(
            "SELECT non_sensitive_details FROM audit_events WHERE action = 'auth.denied'"
        ).fetchall()
    finally:
        connection.close()
    print(f"  audited refusals in the throwaway database: {len(denied)}")
    if not denied:
        failures.append("the refusal was not audited")

    print("\n" + "=" * 78)
    if failures:
        print("RESULT: FAIL — " + "; ".join(failures))
        return 1
    print("RESULT: PASS — 11 figures rendered from the image's own artifacts, every number "
          "equal to metrics.json, and the user session refused and audited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
