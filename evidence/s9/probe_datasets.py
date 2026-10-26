"""S9 acceptance probe: the dataset manager's service layer, end to end, with real files.

Run inside the built image so the dependency set is the deployed one:

    docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:s9 \
        python evidence/s9/probe_datasets.py

Three phases, each printing only what it measured:

A. the seed CSV validates and stages — counts, checksum, class balance, preview aggregates;
B. two malformed uploads are rejected — the reason, the stable codes, the persisted row;
C. activation and a restart — the pointer survives, the model artifact hash does not move.

The administrator's password is generated in this process and never printed. A temporary
database and quarantine directory are created under /tmp inside the container.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src import data_manager, db, security

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "UCI_Credit_Card.csv"
MODELS = ROOT / "models"
ARTIFACT = MODELS / "best_pipeline.joblib"
MANIFEST = MODELS / "model_manifest.json"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def heading(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def bootstrap(connection: sqlite3.Connection) -> str:
    """Create one administrator the way the setup script does, then sign in."""
    password = f"probe-{secrets.token_hex(8)}-s9"
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES ('probe_admin', 'Probe Admin', ?, 'admin', 1, 0, ?, ?, NULL)",
            (security.hash_password(password), moment, moment),
        )
    _, token = security.login(connection, "probe_admin", password)
    print("signed in as: probe_admin (password generated in-process, not printed)")
    return token


def audit_actions(connection: sqlite3.Connection) -> list[str]:
    return [
        row["action"] for row in connection.execute("SELECT action FROM audit_events ORDER BY id")
    ]


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="s9-probe-"))
    db_path = workdir / "probe.db"
    quarantine = workdir / "quarantine"
    print(f"database:  {db_path}")
    print(f"quarantine: {quarantine}")
    print(f"seed file: {SEED} ({SEED.stat().st_size:,} bytes)")

    connection = db.connect(db_path)
    db.migrate(connection)
    print("migrations applied:", [r["version"] for r in connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version")])

    token = bootstrap(connection)

    heading("A. the seed CSV: validate, stage, and what the preview exposes")
    artifact_before = sha256_of(ARTIFACT)
    manifest_before = sha256_of(MANIFEST)
    print("model artifact sha256 before:", artifact_before)
    print("manifest sha256 before:     ", manifest_before)

    seed_version = data_manager.ensure_seed_version(connection)
    print("seed registered as version:", seed_version.id,
          "| active:", seed_version.is_active,
          "| status:", seed_version.status,
          "| records:", seed_version.record_count,
          "| columns:", seed_version.column_count,
          "| class 0:", seed_version.class_zero,
          "| class 1:", seed_version.class_one)

    staged = data_manager.stage_upload(
        connection, token, SEED.read_bytes(), "UCI_Credit_Card.csv", quarantine_dir=quarantine
    )
    version = staged.version
    print("stage_upload -> duplicate:", staged.duplicate, "(the seed is already version 1)")
    print("version row:", {
        "id": version.id,
        "records": version.record_count,
        "columns": version.column_count,
        "class_zero": version.class_zero,
        "class_one": version.class_one,
        "sha256": version.sha256,
        "status": version.status,
        "is_active": version.is_active,
        "validated_at": version.validated_at,
    })
    print("sha256 equals the manifest's dataset sha256:",
          version.sha256 == data_manager.deployed_model_facts(MODELS)["dataset_sha256"])

    subset = pd.read_csv(SEED).head(400)
    staged = data_manager.stage_upload(
        connection, token, subset.to_csv(index=False).encode(), "first_400_rows.csv",
        quarantine_dir=quarantine,
    )
    print("staged a 400-row subset as version", staged.version.id,
          "| records:", staged.version.record_count,
          "| class 0:", staged.version.class_zero,
          "| class 1:", staged.version.class_one,
          "| status:", staged.version.status,
          "| active:", staged.version.is_active)
    print("quarantined under generated name:", staged.version.quarantined_filename)
    print("file exists in quarantine:",
          (quarantine / str(staged.version.quarantined_filename)).is_file())
    print("original filename stored as a label only:", staged.version.original_filename_safe)
    preview = staged.preview
    print("preview rows (one per column, no records):", len(preview.columns))
    for name in ("AGE", "LIMIT_BAL", "PAY_0"):
        column = next(c for c in preview.columns if c.name == name)
        print(f"  {column.name:10s} min={column.minimum:<8} max={column.maximum:<9} "
              f"mean={column.mean:<10} distinct={column.distinct}")
    print("preview has a raw-records attribute:", hasattr(preview, "records"))

    heading("B. two malformed uploads, refused and recorded")
    bad_frames = {
        "missing_pay6.csv": pd.read_csv(SEED).head(25).drop(columns=["PAY_6"]),
        "wrong_target.csv": pd.read_csv(SEED).head(25).assign(
            **{"default.payment.next.month": 2}
        ),
    }
    for filename, frame in bad_frames.items():
        try:
            data_manager.stage_upload(
                connection, token, frame.to_csv(index=False).encode(), filename,
                quarantine_dir=quarantine,
            )
        except data_manager.DatasetRejected as rejected:
            print()
            print(f"upload {filename!r} -> DatasetRejected #{rejected.rejection_id}")
            print("  codes: ", sorted(rejected.report.codes))
            print("  reason:", rejected.reason)
    print()
    print("rejection log rows:")
    for row in data_manager.list_rejections(connection, token):
        print(" ", {"id": row["id"], "file": row["original_filename_safe"],
                    "codes": row["error_codes"], "reason": row["reason"],
                    "quarantined_copy": row["quarantined_filename"]})
    print("dataset_versions still holds only validated uploads:",
          [v.status for v in data_manager.list_versions(connection, token)])
    print("quarantine directory contents after rejections:",
          sorted(p.name for p in quarantine.glob("*")))
    print("audit actions so far:", audit_actions(connection))

    heading("C. activation, then a restart: pointer persists, artifact does not move")
    activated = data_manager.activate_version(connection, token, staged.version.id)
    print("activated version:", activated.id, "| is_active:", activated.is_active,
          "| activated_at:", activated.activated_at, "| status:", activated.status)
    comparison = data_manager.comparison(connection, token)
    print("page verdict — active dataset built the deployed model:",
          comparison["active_built_the_model"])
    print("deployed model dataset sha256:", comparison["deployed"]["dataset_sha256"])
    print("artifact sha256 recorded in manifest:",
          comparison["deployed"]["artifact_sha256_recorded"])
    print("artifact sha256 on disk now:        ",
          comparison["deployed"]["artifact_sha256_now"])

    connection.close()
    print()
    print("-- restart: new connection to the same file --")
    connection = db.connect(db_path)
    active_after = data_manager.active_version(connection, token)
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM dataset_versions WHERE is_active = 1").fetchone()["n"]
    print("active version after restart:", active_after.id, "| sha256:", active_after.sha256,
          "| status:", active_after.status)
    print("rows with is_active = 1:", count)
    print("versions on disk:", [(v.id, v.status, v.is_active)
                                for v in data_manager.list_versions(connection, token)])
    data_manager.ensure_seed_version(connection)  # startup runs again
    again = data_manager.active_version(connection, token)
    print("pointer after a second startup:", again.id, "(unchanged)")

    artifact_after = sha256_of(ARTIFACT)
    manifest_after = sha256_of(MANIFEST)
    print()
    print("model artifact sha256 after: ", artifact_after)
    print("manifest sha256 after:       ", manifest_after)
    print("artifact identical before/after upload+activation:",
          artifact_after == artifact_before)
    print("manifest identical before/after upload+activation:",
          manifest_after == manifest_before)

    print()
    print("audit rows for dataset actions:")
    for row in connection.execute(
        "SELECT action, actor_user_id, entity_type, entity_id, non_sensitive_details "
        "FROM audit_events WHERE action LIKE 'dataset.%' ORDER BY id"
    ):
        print(" ", dict(row))

    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
