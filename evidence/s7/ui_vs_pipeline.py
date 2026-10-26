"""S7 acceptance: the numbers on screen equal the pipeline's own numbers.

Three independent paths score the same 23 values:

1. the page, driven through Streamlit's ``AppTest`` harness (sign in → load the synthetic
   example → submit → read the rendered class, probability and band);
2. the command-line interface, ``python -m src.inference --input -``, as a separate process;
3. ``load_service().predict(...)`` in this process.

The script prints all three and fails unless they agree exactly.

Run inside the application image:

    docker run --rm --network none -v "$PWD":/app -w /app -u 1001:1001 \\
        aihubcampus-web:s7 python evidence/s7/ui_vs_pipeline.py
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import db, security

# The Streamlit runtime logs a benign "widget default value also set via session state"
# warning when the demonstrator button fills the form; it is noise in an evidence transcript.
logging.disable(logging.WARNING)
from src.inference import load_service
from src.pages_prediction import DEMO_EXAMPLE

APP_PATH = str(Path(__file__).resolve().parents[2] / "app.py")
USERNAME = "s7-acceptance-user"
PASSWORD = "s7-acceptance-disposable-71"


def _seed(path: str) -> None:
    conn = db.connect(path)
    try:
        db.migrate(conn)
        moment = db.to_iso(db.utcnow())
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                "must_change_password, created_at, updated_at, last_login_at) "
                "VALUES (?, ?, ?, 'user', 1, 0, ?, ?, NULL)",
                (USERNAME, "S7 acceptance", security.hash_password(PASSWORD), moment, moment),
            )
    finally:
        conn.close()


def _on_screen() -> dict[str, str]:
    at = AppTest.from_file(APP_PATH, default_timeout=180)
    at.run()
    at.text_input(key="login_username").set_value(USERNAME)
    at.text_input(key="login_password").set_value(PASSWORD)
    at.button[0].click().run()
    at.sidebar.radio[0].set_value("Predict default risk")
    at = at.run()
    labels = [b.label for b in at.button]
    at.button[labels.index("Load synthetic demonstrator example")].click().run()
    labels = [b.label for b in at.button]
    at = at.button[labels.index("Predict default risk")].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    markdown = [m.value for m in at.markdown]
    class_line = next(m for m in markdown if m.startswith("#### Predicted"))
    probability_line = next(m for m in markdown if m.startswith("Estimated model probability"))
    band_line = next(m for m in markdown if m.startswith("**Risk band:"))
    return {
        "class_line": class_line.removeprefix("#### "),
        "probability_line": probability_line,
        "band_line": band_line.strip("*"),
    }


def _cli() -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "src.inference", "--input", "-"],
        input=json.dumps(DEMO_EXAMPLE),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def main() -> int:
    workdir = tempfile.mkdtemp(prefix="s7-acceptance-")
    os.environ["APP_DB_PATH"] = os.path.join(workdir, "acceptance.db")
    _seed(os.environ["APP_DB_PATH"])

    screen = _on_screen()
    pipeline = load_service().predict(DEMO_EXAMPLE)
    cli = _cli()

    expected_probability = f"{pipeline.probability:.2%}"
    print("Input: the synthetic demonstrator row from src/pages_prediction.py DEMO_EXAMPLE")
    print(json.dumps(DEMO_EXAMPLE, sort_keys=True))
    print()
    print("1) on screen (Streamlit AppTest, real page):")
    print(f"   class       : {screen['class_line']}")
    print(f"   probability : {screen['probability_line']}")
    print(f"   band        : {screen['band_line']}")
    print()
    print("2) CLI (python -m src.inference --input -):")
    print(f"   class       : {cli['class_label']}")
    print(f"   probability : {cli['probability']:.6f}")
    print(f"   band        : {cli['tier_label']}")
    print(f"   version     : {cli['model_version']}")
    print()
    print("3) loaded pipeline (load_service().predict):")
    print(f"   class       : {pipeline.class_label}")
    print(f"   probability : {pipeline.probability:.6f}")
    print(f"   band        : {pipeline.tier_label}")
    print(f"   version     : {pipeline.model_version}")
    print()

    checks = {
        "screen class == pipeline class": screen["class_line"] == pipeline.class_label,
        "screen probability == pipeline probability (2 dp)": expected_probability
        in screen["probability_line"],
        "screen band == pipeline band": screen["band_line"] == f"Risk band: {pipeline.tier_label}",
        "CLI class == pipeline class": cli["class_label"] == pipeline.class_label,
        "CLI probability == pipeline probability": abs(cli["probability"] - pipeline.probability)
        == 0.0,
        "CLI band == pipeline band": cli["tier_label"] == pipeline.tier_label,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
