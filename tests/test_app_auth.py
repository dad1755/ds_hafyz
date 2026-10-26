"""Sprint 6 UI gate: the page signs in for real, and hides nothing that the server allows.

The S1 test asserted that the sign-in shell *never* authenticated. That shell is gone; this
file replaces it and asserts the opposite properties, each against a real SQLite file:

* an anonymous visitor sees only the sign-in form — no account list, no audit trail;
* a wrong password produces one generic error and no session;
* a correct password opens a session, and the page then shows the role it actually has;
* a regular user never sees the admin section, and the caption says the server refuses those
  calls regardless;
* a forced password change blocks the whole page until a compliant password is set;
* signing out revokes the session row and returns to the form;
* nothing typed into the form is echoed back into the page.

These run with Streamlit's own ``AppTest`` harness, so they execute ``app.py`` exactly as the
server does, against ``APP_DB_PATH`` pointing at a temporary database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import db, security

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

ADMIN_USERNAME = "admin_one"
ADMIN_PASSWORD = "amber-quartz-heron-91"
USER_USERNAME = "demo_user"
USER_PASSWORD = "violet-anchor-lamp-27"


def _seed(connection: sqlite3.Connection, username: str, password: str, role: str,
          must_change: bool = False) -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, NULL)",
            (
                username,
                username.replace("_", " ").title(),
                security.hash_password(password),
                role,
                1 if must_change else 0,
                moment,
                moment,
            ),
        )


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    connection = db.connect(path)
    try:
        db.migrate(connection)
        _seed(connection, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
        _seed(connection, USER_USERNAME, USER_PASSWORD, "user")
    finally:
        connection.close()
    return path


def _app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=90)
    at.run()
    return at


def _sign_in(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input(key="login_username").set_value(username)
    at.text_input(key="login_password").set_value(password)
    return at.button[0].click().run()


def _rendered(at: AppTest) -> str:
    return " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [s.value for s in at.success]
        + [e.value for e in at.error]
        + [w.value for w in at.warning]
    )


def _session_count(path: Path) -> int:
    connection = db.connect(path)
    try:
        return connection.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    finally:
        connection.close()


def test_anonymous_visitor_sees_only_the_sign_in_form(app_db):
    at = _app()

    assert not at.exception
    assert at.title[0].value == "AI Hub Campus"
    assert at.subheader[0].value == "Credit Card Default Risk Prediction"
    assert [i.label for i in at.text_input] == ["Username", "Password"]
    assert [b.label for b in at.button] == ["Sign in"]

    rendered = _rendered(at)
    assert "#### Accounts" not in rendered
    assert "Recent audit events" not in rendered
    assert _session_count(app_db) == 0


def test_a_wrong_password_shows_one_generic_error_and_opens_no_session(app_db):
    at = _sign_in(_app(), ADMIN_USERNAME, "definitely-not-the-password")

    assert not at.exception
    assert [e.value for e in at.error] == ["Invalid username or password."]
    assert _session_count(app_db) == 0
    # Still the sign-in form, not a signed-in page.
    assert [b.label for b in at.button] == ["Sign in"]


def test_the_page_never_echoes_what_was_typed(app_db):
    at = _sign_in(_app(), "probe-user-xyz", "probe-secret-xyz")

    rendered = _rendered(at)
    assert "probe-user-xyz" not in rendered
    assert "probe-secret-xyz" not in rendered


def test_an_admin_signs_in_and_sees_the_admin_section(app_db):
    at = _sign_in(_app(), ADMIN_USERNAME, ADMIN_PASSWORD)

    assert not at.exception
    rendered = _rendered(at)
    assert "Signed in as" in rendered
    assert "Authentication is live" in rendered
    assert "#### Accounts" in rendered
    assert "Recent audit events" in rendered
    assert _session_count(app_db) == 1
    # The sign-in form is gone; the only button left is sign-out.
    assert [b.label for b in at.button] == ["Sign out"]


def test_a_regular_user_never_sees_the_admin_section(app_db):
    at = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)

    assert not at.exception
    rendered = _rendered(at)
    assert "Signed in as" in rendered
    assert "#### Accounts" not in rendered
    assert "Recent audit events" not in rendered
    assert "not available to your role" in rendered


def test_a_forced_password_change_blocks_the_page_until_it_is_done(tmp_path, monkeypatch):
    path = tmp_path / "forced.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    connection = db.connect(path)
    try:
        db.migrate(connection)
        _seed(connection, "operator", "short-pw", "admin", must_change=True)
    finally:
        connection.close()

    at = _sign_in(_app(), "operator", "short-pw")

    assert not at.exception
    rendered = _rendered(at)
    assert "Set a new password" in rendered
    assert "#### Accounts" not in rendered  # the admin section is unreachable until changed

    # A password that breaks the policy is refused with the rule, not the value.
    at.text_input(key="cp_current").set_value("short-pw")
    at.text_input(key="cp_new").set_value("short")
    at.text_input(key="cp_confirm").set_value("short")
    at = at.button[0].click().run()
    assert "at least 12 characters" in " ".join(e.value for e in at.error)

    # A compliant password clears the flag and lands on the signed-in page.
    at.text_input(key="cp_current").set_value("short-pw")
    at.text_input(key="cp_new").set_value("willow-cobalt-finch-63")
    at.text_input(key="cp_confirm").set_value("willow-cobalt-finch-63")
    at = at.button[0].click().run()

    assert not at.exception
    rendered = _rendered(at)
    assert "Password changed" in rendered or "Signed in as" in rendered
    assert "#### Accounts" in rendered


def test_signing_out_revokes_the_session_and_returns_to_the_form(app_db):
    at = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)
    assert _session_count(app_db) == 1

    at = at.button[0].click().run()  # "Sign out"

    assert not at.exception
    assert [b.label for b in at.button] == ["Sign in"]
    assert _session_count(app_db) == 1  # the row stays, revoked — the audit trail keeps it
    connection = db.connect(app_db)
    try:
        row = connection.execute("SELECT revoked_at FROM sessions").fetchone()
        assert row["revoked_at"] is not None
    finally:
        connection.close()
