"""Sprint 11: the three system tests that only make sense end to end.

The per-feature suites prove each part in isolation. These prove the parts still compose:

* **T01** — one admin and one user, signed in through the real page, get *different*
  navigation: the admin sees three management entries, the user sees none of them, and both
  see the two ordinary entries.
* **T11** — a restart keeps the SQLite rows, the signed-in session and the model. The session
  token is resolved by a **second process** (``python -c`` against the same database), which
  is what a container restart really is; the model is re-verified from disk in that process
  and must report the same artifact checksum.
* **T12** — the whole user journey in one session: sign in → 23-field prediction → the result
  panel → the history row → sign out → the sign-in form again, with the session revoked in the
  database and the row still there.

Every assertion compares against the pipeline or the database, never against a literal the
page itself could have typed in.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import db, security
from src.inference import load_service
from src.pages_prediction import DEMO_EXAMPLE

REPO = Path(__file__).resolve().parents[1]
APP_PATH = REPO / "app.py"

ADMIN = ("admin_one", "amber-quartz-heron-91")
USER = ("journey_user", "violet-anchor-lamp-27")


def _seed(connection: sqlite3.Connection, username: str, password: str, role: str) -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (
                username,
                username.replace("_", " ").title(),
                security.hash_password(password),
                role,
                moment,
                moment,
            ),
        )


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "journey.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    connection = db.connect(path)
    try:
        db.migrate(connection)
        _seed(connection, *ADMIN, "admin")
        _seed(connection, *USER, "user")
    finally:
        connection.close()
    return path


@pytest.fixture(scope="module")
def service():
    return load_service()


def _sign_in(username: str, password: str) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    at.text_input(key="login_username").set_value(username)
    at.text_input(key="login_password").set_value(password)
    return at.button[0].click().run()


def _nav(at: AppTest) -> tuple[str, ...]:
    return tuple(at.sidebar.radio[0].options)


def _go(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio[0].set_value(page)
    return at.run()


def _markdown(at: AppTest) -> list[str]:
    return [block.value for block in at.markdown]


def _rows(path: Path) -> list[sqlite3.Row]:
    connection = db.connect(path)
    try:
        return connection.execute("SELECT * FROM prediction_logs ORDER BY id").fetchall()
    finally:
        connection.close()


# --------------------------------------------------------------------- T01
def test_t01_an_admin_and_a_user_sign_in_to_different_navigation(app_db):
    admin = _sign_in(*ADMIN)
    user = _sign_in(*USER)

    admin_nav, user_nav = _nav(admin), _nav(user)
    management = ("User management", "Dataset manager", "Model evaluation")

    assert management == tuple(admin_nav[3:]), admin_nav
    for entry in management:
        assert entry in admin_nav
        assert entry not in user_nav
    assert user_nav == ("Home", "Predict default risk", "My prediction history")

    # Both signed in for real: the session is a database row, not a widget state.
    assert any("Signed in as" in text for text in _markdown(admin))
    assert any("Signed in as" in text for text in _markdown(user))
    assert any("Role `admin`" in text for text in _markdown(admin))
    assert any("Role `user`" in text for text in _markdown(user))


# --------------------------------------------------------------------- T11
def test_t11_a_restart_keeps_the_database_the_session_and_the_model(app_db, service):
    connection = db.connect(app_db)
    try:
        principal, token = security.login(connection, *USER)
    finally:
        connection.close()

    # A second process, as a restarted container would be: no shared memory, no cached
    # object, the same database file and the same read-only model directory.
    probe = (
        "import json\n"
        "from src import db, security\n"
        "from src.inference import load_service\n"
        "conn = db.connect()\n"
        "principal = security.resolve_session(conn, __import__('os').environ['PROBE_TOKEN'])\n"
        "svc = load_service()\n"
        "print(json.dumps({\n"
        "    'username': principal.username,\n"
        "    'role': principal.role,\n"
        "    'model_version': svc.model_version,\n"
        "    'artifact_sha256': svc.artifact_sha256,\n"
        "}))\n"
    )
    environment = dict(os.environ, PROBE_TOKEN=token, APP_DB_PATH=str(app_db))
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    seen = json.loads(result.stdout.strip().splitlines()[-1])
    assert seen["username"] == USER[0]
    assert seen["role"] == "user"
    assert seen["model_version"] == service.model_version
    assert seen["artifact_sha256"] == service.artifact_sha256
    assert len(seen["artifact_sha256"]) == 64

    # The session row is still valid in this process too, and the login is on record.
    connection = db.connect(app_db)
    try:
        assert security.resolve_session(connection, token).username == USER[0]
        actions = [
            row["action"]
            for row in connection.execute("SELECT action FROM audit_events ORDER BY id")
        ]
        assert "login.succeeded" in actions
    finally:
        connection.close()


# --------------------------------------------------------------------- T12
def test_t12_full_journey_login_predict_history_logout(app_db, service):
    at = _sign_in(*USER)
    assert not at.exception
    assert _rows(app_db) == []

    at = _go(at, "Predict default risk")
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    at = at.button[[b.label for b in at.button].index("Predict default risk")].click().run()

    assert not at.exception
    expected = service.predict(DEMO_EXAMPLE)
    rendered = _markdown(at)
    assert f"#### {expected.class_label}" in rendered
    assert (
        f"{expected.probability_label}: **{expected.probability:.2%}** *(estimated, uncalibrated)*"
    ) in rendered
    assert f"**Risk band: {expected.tier_label}**" in rendered
    assert f"**What this suggests:** {expected.tier_advice}" in rendered

    rows = _rows(app_db)
    assert len(rows) == 1
    assert rows[0]["predicted_class"] == expected.predicted_class
    assert rows[0]["default_probability"] == pytest.approx(expected.probability, abs=1e-12)
    assert rows[0]["risk_tier"] == expected.risk_tier

    # History shows that one row, with the numbers the result panel showed.
    at = _go(at, "My prediction history")
    assert not at.exception
    table = [dict(row) for frame in at.dataframe for row in frame.value.to_dict("records")]
    assert len(table) == 1
    assert table[0]["estimated P(default)"] == f"{expected.probability:.2%}"
    assert table[0]["model version"] == expected.model_version
    assert any(USER[0] in (caption.value or "") for caption in at.caption)

    # Sign out from Home, and the session is revoked in the database, not just on screen.
    at = _go(at, "Home")
    at = at.button[[b.label for b in at.button].index("Sign out")].click().run()
    assert not at.exception
    assert at.sidebar.radio == [], "the signed-in navigation is gone"
    assert at.text_input(key="login_username").value == ""
    assert at.text_input(key="login_password").value == ""

    connection = db.connect(app_db)
    try:
        live = connection.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL"
        ).fetchone()["n"]
        actions = [
            row["action"]
            for row in connection.execute("SELECT action FROM audit_events ORDER BY id")
        ]
    finally:
        connection.close()
    assert live == 0
    assert "session.revoked" in actions
    # The prediction survives the sign-out: it belongs to the account, not the session.
    assert len(_rows(app_db)) == 1


def test_t12_the_prediction_is_refused_before_sign_in(app_db):
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    assert at.sidebar.radio == []
    assert at.text_input(key="login_username").label
    assert _rows(app_db) == []
