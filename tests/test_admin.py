"""Sprint 8 gate: administrator user management, driven through the real page.

The card asks for one outcome — an administrator can list, create, edit, reset and deactivate
accounts, every action is audited, and the installation cannot be orphaned — plus five specific
tests. Each of those five has a test here, written so it fails if the *implementation*
regresses rather than if a label changes:

1. an account created in the admin UI can then sign in (``test_an_admin_creates_an_account_...``);
2. a role change takes effect on the next request, not the next sign-in;
3. a user calling an admin function is denied **and** the attempt is audited, with the row
   quoted back;
4. the last enabled admin cannot be demoted or deactivated, from the UI as well as the service;
5. no password hash and no plaintext password is ever rendered, audited or logged.

Two further properties are asserted because the card states them as guardrails: there is no
delete path anywhere in the source, and there is no self-registration widget on the sign-in
page.

Half the tests go through Streamlit's ``AppTest`` harness, so they execute ``app.py`` exactly as
the server does, against ``APP_DB_PATH`` pointing at a temporary database. The other half call
the service functions directly, which is the path an attacker would take.

Sprint 9 continues in the same file (from ``SPRINT 9`` below): the dataset manager. Those tests
stage the real seed CSV, quote the counts it produces, paste two malformed uploads' rejection
reasons, and hash the model artifact before and after an upload and activation to show the
deployed model is untouched.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import accounts, data_manager, db, security
from src.security import (
    InvalidCredentials,
    PasswordChangeRequired,
    PermissionDenied,
    PolicyViolation,
    SessionInvalid,
)

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"

ADMIN_USERNAME = "admin_one"
ADMIN_PASSWORD = "amber-quartz-heron-91"
USER_USERNAME = "demo_user"
USER_PASSWORD = "violet-anchor-lamp-27"
NEW_PASSWORD = "copper-basalt-moth-58"
TEMPORARY_PASSWORD = "willow-cobalt-finch-63"
NEW_ACCOUNT_PASSWORD = "harbour-lantern-quill-84"

SECTION = "User management"


# --------------------------------------------------------------------------- fixtures
def _seed(connection: sqlite3.Connection, username: str, password: str, role: str) -> int:
    """Insert an account the way the setup script does — hashed, never plaintext."""
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        cursor = connection.execute(
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
    return int(cursor.lastrowid)


@pytest.fixture()
def conn(tmp_path):
    connection = db.connect(tmp_path / "admin.db")
    db.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    """A temporary database for the AppTest runs, with one admin and one user."""
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


def _admin_token(conn) -> str:
    _, token = security.login(conn, ADMIN_USERNAME, ADMIN_PASSWORD)
    return token


def _user_token(conn) -> str:
    _, token = security.login(conn, USER_USERNAME, USER_PASSWORD)
    return token


def _row(conn, sql: str, params: tuple = ()) -> sqlite3.Row:
    return conn.execute(sql, params).fetchone()


# ------------------------------------------------------------------------ AppTest helpers
def _app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    return at


def _sign_in(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input(key="login_username").set_value(username)
    at.text_input(key="login_password").set_value(password)
    return at.button[0].click().run()


def _admin_page(username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD) -> AppTest:
    at = _sign_in(_app(), username, password)
    at.sidebar.radio[0].set_value(SECTION)
    return at.run()


def _click(at: AppTest, label: str, occurrence: int = 0) -> AppTest:
    """Click the nth button carrying this label (several accounts share one label)."""
    matches = [button for button in at.button if button.label == label]
    assert matches, f"no button labelled {label!r}; labels were {[b.label for b in at.button]}"
    return matches[occurrence].click().run()


def _rendered(at: AppTest) -> str:
    """Every string the page put on screen, including the table cells."""
    cells = []
    for frame in at.dataframe:
        records = frame.value.to_dict("records")
        cells.extend(str(value) for record in records for value in record.values())
    return " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [s.value for s in at.success]
        + [e.value for e in at.error]
        + [w.value for w in at.warning]
        + [i.value for i in at.info]
        + cells
    )


def _table_columns(at: AppTest) -> list[str]:
    return [str(column) for frame in at.dataframe for column in frame.value.columns]


def _user_id(path: Path, username: str) -> int:
    connection = db.connect(path)
    try:
        return int(
            connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()[
                "id"
            ]
        )
    finally:
        connection.close()


def _position(path: Path, username: str) -> int:
    """Where this account sits in the page's list, which is ordered by ``lower(username)``."""
    connection = db.connect(path)
    try:
        names = [
            row["username"]
            for row in connection.execute("SELECT username FROM users ORDER BY lower(username)")
        ]
    finally:
        connection.close()
    return names.index(username)


def _display_key(path: Path, username: str) -> str:
    return f"admin_display_{_user_id(path, username)}"


def _role_key(path: Path, username: str) -> str:
    return f"admin_role_select_{_user_id(path, username)}"


def _password_keys(path: Path, username: str) -> tuple[str, str]:
    user_id = _user_id(path, username)
    return f"admin_password_new_{user_id}", f"admin_password_confirm_{user_id}"


# ------------------------------------------- 1. an admin provisions a user who signs in
def test_an_admin_creates_an_account_in_the_ui_and_that_user_then_signs_in(app_db):
    at = _admin_page()
    assert not at.exception
    assert "### User management" in [m.value for m in at.markdown]

    at.text_input(key="admin_new_username").set_value("provisioned_user")
    at.text_input(key="admin_new_display_name").set_value("Provisioned User")
    at.text_input(key="admin_new_password").set_value(NEW_ACCOUNT_PASSWORD)
    at.text_input(key="admin_new_password_confirm").set_value(NEW_ACCOUNT_PASSWORD)
    at = _click(at, "Create account")

    assert not at.exception
    assert "Account **provisioned_user** created with role `user`" in _rendered(at)
    # The password that was typed is not on the page, in any form.
    assert NEW_ACCOUNT_PASSWORD not in _rendered(at)
    assert "$argon2id$" not in _rendered(at)

    connection = db.connect(app_db)
    try:
        created = connection.execute(
            "SELECT username, display_name, role, is_active, password_hash FROM users "
            "WHERE username = 'provisioned_user'"
        ).fetchone()
    finally:
        connection.close()
    assert created is not None
    assert created["display_name"] == "Provisioned User"
    assert created["role"] == "user"
    assert created["is_active"] == 1
    assert created["password_hash"].startswith(security.HASH_PREFIX)
    assert NEW_ACCOUNT_PASSWORD not in created["password_hash"]

    # The provisioned account can actually sign in — the whole point of the card.
    signed_in = _sign_in(_app(), "provisioned_user", NEW_ACCOUNT_PASSWORD)
    assert not signed_in.exception
    rendered = _rendered(signed_in)
    assert "Signed in as" in rendered
    assert "Signed in as" in rendered and "Provisioned User" in rendered
    assert [b.label for b in signed_in.button] == ["Sign out"]
    # …and it is a user, not an admin: no administration entry in the navigation.
    assert SECTION not in [option for option in signed_in.sidebar.radio[0].options]
    assert SECTION not in rendered


def test_a_created_account_cannot_duplicate_an_existing_username(app_db):
    at = _admin_page()
    at.text_input(key="admin_new_username").set_value(USER_USERNAME)
    at.text_input(key="admin_new_password").set_value(NEW_ACCOUNT_PASSWORD)
    at.text_input(key="admin_new_password_confirm").set_value(NEW_ACCOUNT_PASSWORD)
    at = _click(at, "Create account")

    assert not at.exception
    assert [e.value for e in at.error] == ["That username is already taken."]
    assert "created with role" not in _rendered(at)


def test_a_weak_or_mismatched_password_is_refused_without_echoing_it(app_db):
    at = _admin_page()
    at.text_input(key="admin_new_username").set_value("weak_user")
    at.text_input(key="admin_new_password").set_value("short")
    at.text_input(key="admin_new_password_confirm").set_value("short")
    at = _click(at, "Create account")

    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "at least 12 characters" in errors
    assert "short" not in errors

    at.text_input(key="admin_new_username").set_value("mismatch_user")
    at.text_input(key="admin_new_password").set_value(NEW_ACCOUNT_PASSWORD)
    at.text_input(key="admin_new_password_confirm").set_value(NEW_ACCOUNT_PASSWORD + "x")
    at = _click(at, "Create account")
    assert [e.value for e in at.error] == ["The two passwords do not match."]

    connection = db.connect(app_db)
    try:
        names = [row["username"] for row in connection.execute("SELECT username FROM users")]
    finally:
        connection.close()
    assert "weak_user" not in names and "mismatch_user" not in names


# ---------------------------------------- 2. a role change takes effect on the next request
def test_a_role_change_takes_effect_on_the_next_request(conn):
    admin_id = _seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
    _seed(conn, USER_USERNAME, USER_PASSWORD, "user")
    admin_token = _admin_token(conn)
    user_session = _user_token(conn)

    # Same session token, before the change: denied.
    with pytest.raises(PermissionDenied):
        accounts.list_users(conn, user_session)

    user_id = _row(conn, "SELECT id FROM users WHERE username = ?", (USER_USERNAME,))["id"]
    accounts.set_role(conn, admin_token, user_id, "admin")

    # Same session token, after the change: the next request is authorised, with no new
    # sign-in, because require_role re-reads the row on every call.
    promoted = accounts.list_users(conn, user_session)
    assert {user.username for user in promoted} == {ADMIN_USERNAME, USER_USERNAME}

    # And the reverse, on the same token.
    accounts.set_role(conn, admin_token, user_id, "user")
    with pytest.raises(PermissionDenied):
        accounts.list_users(conn, user_session)

    assert _row(conn, "SELECT role FROM users WHERE id = ?", (admin_id,))["role"] == "admin"


def test_the_ui_role_change_persists_and_is_audited(app_db):
    at = _admin_page()
    at.selectbox(key=_role_key(app_db, USER_USERNAME)).set_value("admin")
    at = _click(at, "Save role", occurrence=_position(app_db, USER_USERNAME))

    assert not at.exception
    assert "Role for **demo_user** is now `admin`" in _rendered(at)

    connection = db.connect(app_db)
    try:
        assert _row(connection, "SELECT role FROM users WHERE username = 'demo_user'")["role"] == "admin"
        row = _row(
            connection,
            "SELECT action, entity_id, non_sensitive_details FROM audit_events "
            "WHERE action = 'user.role_changed' ORDER BY id DESC LIMIT 1",
        )
    finally:
        connection.close()
    assert row["action"] == "user.role_changed"
    assert '"from":"user"' in row["non_sensitive_details"]
    assert '"to":"admin"' in row["non_sensitive_details"]


def test_a_display_name_edit_persists_and_is_audited(app_db):
    at = _admin_page()
    at.text_input(key=_display_key(app_db, USER_USERNAME)).set_value("Renamed Account")
    at = _click(at, "Save display name", occurrence=_position(app_db, USER_USERNAME))

    assert not at.exception
    assert "Display name for **demo_user** saved." in _rendered(at)

    connection = db.connect(app_db)
    try:
        assert (
            _row(connection, "SELECT display_name FROM users WHERE username = 'demo_user'")[
                "display_name"
            ]
            == "Renamed Account"
        )
        actions = [
            row["action"]
            for row in connection.execute("SELECT action FROM audit_events ORDER BY id")
        ]
    finally:
        connection.close()
    assert "user.display_name_changed" in actions


# --------------------------------- 3. forbidden attempts are denied AND audited
PRIVILEGED_CALLS = {
    "list_users": lambda c, t, target: accounts.list_users(c, t),
    "get_user": lambda c, t, target: accounts.get_user(c, t, target),
    "recent_audit_events": lambda c, t, target: accounts.recent_audit_events(c, t),
    "create_user": lambda c, t, target: accounts.create_user(
        c, t, username="planted_admin", password=NEW_PASSWORD, role="admin"
    ),
    "set_display_name": lambda c, t, target: accounts.set_display_name(c, t, target, "Hijacked"),
    "set_role": lambda c, t, target: accounts.set_role(c, t, target, "user"),
    "set_active": lambda c, t, target: accounts.set_active(c, t, target, False),
    "reset_password": lambda c, t, target: accounts.reset_password(c, t, target, NEW_PASSWORD),
}


@pytest.mark.parametrize("call_name", sorted(PRIVILEGED_CALLS))
def test_a_user_calling_an_admin_function_is_denied_and_the_attempt_is_audited(
    conn, call_name
):
    admin_id = _seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
    _seed(conn, USER_USERNAME, USER_PASSWORD, "user")
    token = _user_token(conn)
    before = [tuple(row) for row in conn.execute("SELECT id, role, is_active FROM users ORDER BY id")]

    with pytest.raises(PermissionDenied):
        PRIVILEGED_CALLS[call_name](conn, token, admin_id)

    after = [tuple(row) for row in conn.execute("SELECT id, role, is_active FROM users ORDER BY id")]
    assert after == before, "a denied call must not change any account"

    row = _row(
        conn,
        "SELECT actor_user_id, action, entity_type, non_sensitive_details FROM audit_events "
        "WHERE action = 'auth.denied' ORDER BY id DESC LIMIT 1",
    )
    assert row is not None, "a denied privileged call must be audited"
    assert row["action"] == "auth.denied"
    assert row["actor_user_id"] == _row(
        conn, "SELECT id FROM users WHERE username = ?", (USER_USERNAME,)
    )["id"]
    assert row["entity_type"] == "role"
    # The row names what was attempted — without naming any credential.
    assert f'"attempted":"accounts.{call_name}"' in row["non_sensitive_details"]
    assert '"required":"admin"' in row["non_sensitive_details"]


def test_a_user_never_sees_the_user_management_section(app_db):
    at = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)

    assert not at.exception
    assert SECTION not in at.sidebar.radio[0].options
    assert "User management" not in _rendered(at)
    assert "Create an account" not in _rendered(at)
    # The caption says the server refuses these calls even if the page were bypassed.
    assert "not available to your role" in _rendered(at)


def test_an_anonymous_visitor_gets_only_the_sign_in_form(app_db):
    at = _app()

    assert not at.exception
    assert [i.label for i in at.text_input] == ["Username", "Password"]
    assert [b.label for b in at.button] == ["Sign in"]
    assert at.sidebar.radio == []
    assert "Create an account" not in _rendered(at)


def test_there_is_no_self_registration_anywhere_in_the_source():
    """The only way an account comes into existence is ``accounts.create_user``, admin-gated."""
    for path in SRC_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for needle in ("register_user", "sign_up", "signup", "self_registration"):
            assert needle not in source, f"{path.name} contains a self-registration path"

    import src.pages_login as pages_login

    assert not hasattr(pages_login, "render_register")


# --------------------------------------- 4. the last enabled admin cannot be orphaned
def test_the_last_enabled_admin_cannot_be_demoted_or_deactivated(conn):
    admin_id = _seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
    token = _admin_token(conn)

    with pytest.raises(PolicyViolation) as demote:
        accounts.set_role(conn, token, admin_id, "user")
    assert "last enabled administrator cannot be demoted" in demote.value.public_message

    with pytest.raises(PolicyViolation) as deactivate:
        accounts.set_active(conn, token, admin_id, False)
    assert "last enabled administrator cannot be deactivated" in deactivate.value.public_message

    row = _row(conn, "SELECT role, is_active FROM users WHERE id = ?", (admin_id,))
    assert (row["role"], row["is_active"]) == ("admin", 1)


def test_the_last_admin_guard_holds_from_the_ui_too(app_db):
    at = _admin_page()
    at.selectbox(key=_role_key(app_db, ADMIN_USERNAME)).set_value("user")
    at = _click(at, "Save role", occurrence=_position(app_db, ADMIN_USERNAME))

    assert not at.exception
    assert "The last enabled administrator cannot be demoted." in " ".join(
        e.value for e in at.error
    )
    connection = db.connect(app_db)
    try:
        assert _row(connection, "SELECT role FROM users WHERE username = ?", (ADMIN_USERNAME,))[
            "role"
        ] == "admin"
    finally:
        connection.close()

    at = _click(at, "Deactivate account", occurrence=0)
    assert "The last enabled administrator cannot be deactivated." in " ".join(
        e.value for e in at.error
    )
    connection = db.connect(app_db)
    try:
        assert _row(connection, "SELECT is_active FROM users WHERE username = ?", (ADMIN_USERNAME,))[
            "is_active"
        ] == 1
    finally:
        connection.close()


def test_the_guard_holds_when_a_second_admin_is_added_and_then_removed(conn):
    first = _seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
    second = _seed(conn, "admin_two", NEW_PASSWORD, "admin")
    token = _admin_token(conn)

    # Two enabled admins: demoting one is allowed.
    accounts.set_role(conn, token, second, "user")
    assert _row(conn, "SELECT role FROM users WHERE id = ?", (second,))["role"] == "user"

    # Promote again, then deactivate the first: allowed, one admin remains.
    accounts.set_role(conn, token, second, "admin")
    accounts.set_active(conn, token, first, False)

    # Now the second is the last enabled admin and cannot be removed — checked with its own
    # session, because deactivating the first admin ended the session we were using.
    _, second_token = security.login(conn, "admin_two", NEW_PASSWORD)
    with pytest.raises(PolicyViolation):
        accounts.set_active(conn, second_token, second, False)


# --------------------------------------- 5. no hash, no plaintext, anywhere it could leak
def test_the_admin_page_renders_no_hash_and_no_plaintext(app_db):
    at = _admin_page()
    rendered = _rendered(at)

    assert not at.exception
    assert "#### Accounts" in [m.value for m in at.markdown]
    assert "$argon2id$" not in rendered
    assert "$argon2" not in rendered
    for password in (ADMIN_PASSWORD, USER_PASSWORD):
        assert password not in rendered
    # No column of the table could carry a hash, and every cell is a plain account fact.
    columns = _table_columns(at)
    assert columns[:4] == ["username", "display name", "role", "active"]
    assert not any("hash" in column or "password_hash" in column for column in columns)

    connection = db.connect(app_db)
    try:
        hashes = [row["password_hash"] for row in connection.execute("SELECT password_hash FROM users")]
    finally:
        connection.close()
    for stored in hashes:
        assert stored not in rendered


def test_a_temporary_password_is_never_echoed_and_forces_a_change(app_db):
    at = _admin_page()
    new_key, confirm_key = _password_keys(app_db, USER_USERNAME)
    at.text_input(key=new_key).set_value(TEMPORARY_PASSWORD)
    at.text_input(key=confirm_key).set_value(TEMPORARY_PASSWORD)
    at = _click(at, "Set temporary password", occurrence=_position(app_db, USER_USERNAME))

    assert not at.exception
    rendered = _rendered(at)
    assert "A temporary password was set for **demo_user**" in rendered
    assert "not shown here" in rendered
    assert TEMPORARY_PASSWORD not in rendered
    assert "$argon2id$" not in rendered

    # The old password no longer works, the temporary one does, and it must be changed.
    connection = db.connect(app_db)
    try:
        with pytest.raises(InvalidCredentials):
            security.login(connection, USER_USERNAME, USER_PASSWORD)

        principal, forced = security.login(connection, USER_USERNAME, TEMPORARY_PASSWORD)
        assert principal.must_change_password is True
        with pytest.raises(PasswordChangeRequired):
            security.require_authenticated(connection, forced)

        # The audit row names the account and the fact, never the value.
        row = _row(
            connection,
            "SELECT non_sensitive_details FROM audit_events WHERE action = 'password.reset' "
            "ORDER BY id DESC LIMIT 1",
        )
    finally:
        connection.close()
    assert TEMPORARY_PASSWORD not in row["non_sensitive_details"]
    assert "$argon2" not in row["non_sensitive_details"]
    assert '"forced_change":true' in row["non_sensitive_details"]


def test_no_audit_row_anywhere_holds_a_hash_or_a_password(conn):
    """Run every admin write, then sweep the whole audit table for credential material."""
    _seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
    user_id = _seed(conn, USER_USERNAME, USER_PASSWORD, "user")
    token = _admin_token(conn)

    accounts.create_user(
        conn, token, username="audited_user", password=NEW_PASSWORD, display_name="Audited", role="user"
    )
    accounts.set_display_name(conn, token, user_id, "Renamed")
    accounts.set_role(conn, token, user_id, "admin")
    accounts.set_role(conn, token, user_id, "user")
    accounts.reset_password(conn, token, user_id, TEMPORARY_PASSWORD)
    accounts.set_active(conn, token, user_id, False)
    accounts.set_active(conn, token, user_id, True)
    # A freshly created account signs in, then reaches for an admin function and is refused.
    _, intruder = security.login(conn, "audited_user", NEW_PASSWORD)
    with pytest.raises(PermissionDenied):
        accounts.list_users(conn, intruder)

    secrets = (ADMIN_PASSWORD, USER_PASSWORD, NEW_PASSWORD, TEMPORARY_PASSWORD)
    hashes = [
        row["password_hash"] for row in conn.execute("SELECT password_hash FROM users")
    ]
    rows = conn.execute("SELECT action, non_sensitive_details FROM audit_events").fetchall()
    assert rows, "the sweep needs audit rows to inspect"
    for row in rows:
        details = row["non_sensitive_details"]
        assert not any(secret in details for secret in secrets), row["action"]
        assert "$argon2" not in details, row["action"]
        assert not any(stored in details for stored in hashes), row["action"]


def test_the_account_table_has_no_delete_path():
    """Soft deactivation is the only removal mechanism; nothing in src/ deletes an account."""
    offenders = []
    for path in SRC_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8").upper()
        if "DELETE FROM USERS" in source or "DROP TABLE USERS" in source:
            offenders.append(path.name)
    assert offenders == []

    assert not hasattr(accounts, "delete_user")
    assert not hasattr(accounts, "remove_user")


def test_deactivating_from_the_ui_ends_the_session_and_keeps_the_row(app_db):
    # Open a session for the user first, so deactivation has something to revoke.
    connection = db.connect(app_db)
    try:
        _, user_session = security.login(connection, USER_USERNAME, USER_PASSWORD)
    finally:
        connection.close()

    at = _admin_page()
    at = _click(at, "Deactivate account", occurrence=_position(app_db, USER_USERNAME))

    assert not at.exception
    assert "**demo_user** is deactivated" in _rendered(at)
    assert "Nothing was deleted" in _rendered(at)

    connection = db.connect(app_db)
    try:
        row = _row(connection, "SELECT is_active FROM users WHERE username = 'demo_user'")
        assert row["is_active"] == 0
        with pytest.raises(SessionInvalid):
            security.resolve_session(connection, user_session)
        actions = [r["action"] for r in connection.execute("SELECT action FROM audit_events")]
    finally:
        connection.close()
    assert "user.deactivated" in actions

    # The deactivated account cannot sign in, and the row is still there.
    blocked = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)
    assert "This account is not active" in " ".join(e.value for e in blocked.error)

    # Reactivating brings it back. Only one account is inactive, so this label is unique.
    at = _admin_page()
    at = _click(at, "Reactivate account", occurrence=0)
    assert "**demo_user** is active again." in _rendered(at)
    back = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)
    assert "Signed in as" in _rendered(back)


# ============================================================================ SPRINT 9
# Dataset manager: staged dataset vs deployed model dataset.
#
# Every number below is the file's own: 30,000 records, 25 columns, 23,364 non-defaults and
# 6,636 defaults are the counts the shipped seed CSV produces, and its sha256 is the dataset
# sha256 recorded in models/model_manifest.json. The artifact hash is re-computed from disk
# before and after each upload so "the deployed model is untouched" is measured, not asserted.

SEED_CSV = Path(__file__).resolve().parents[1] / "data" / "UCI_Credit_Card.csv"
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
ARTIFACT = MODELS_DIR / "best_pipeline.joblib"
MANIFEST = MODELS_DIR / "model_manifest.json"

#: Whole-file facts, verified against the seed CSV itself (awk over the target column).
SEED_ROWS = 30_000
SEED_COLUMNS = 25
SEED_CLASS_ZERO = 23_364
SEED_CLASS_ONE = 6_636
SEED_SHA256 = "a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1"

SECTION_DATASETS = "Dataset manager"


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_payload() -> bytes:
    return SEED_CSV.read_bytes()


def _frame_from_seed(rows: int | None = None) -> pd.DataFrame:
    frame = pd.read_csv(SEED_CSV)
    return frame if rows is None else frame.head(rows)


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


@pytest.fixture()
def dataset_env(tmp_path, monkeypatch):
    """A database and a quarantine directory of its own, with one admin and one user."""
    db_path = tmp_path / "datasets.db"
    quarantine = tmp_path / "quarantine"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    monkeypatch.setenv("APP_QUARANTINE_DIR", str(quarantine))
    connection = db.connect(db_path)
    try:
        db.migrate(connection)
        _seed(connection, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
        _seed(connection, USER_USERNAME, USER_PASSWORD, "user")
    finally:
        connection.close()
    return {"db": db_path, "quarantine": quarantine}


def _open(env) -> sqlite3.Connection:
    return db.connect(env["db"])


def _admin_token_conn(conn) -> str:
    _, token = security.login(conn, ADMIN_USERNAME, ADMIN_PASSWORD)
    return token


def _dataset_page() -> AppTest:
    at = _sign_in(_app(), ADMIN_USERNAME, ADMIN_PASSWORD)
    at.sidebar.radio[0].set_value(SECTION_DATASETS)
    return at.run()


def _stage(at: AppTest, filename: str, payload: bytes) -> AppTest:
    at.file_uploader(key="dataset_file").set_value((filename, payload, "text/csv"))
    at.button(key="dataset_stage_button").click()
    return at.run()


# ------------------------------------------------ 1. the seed CSV stages, with real counts
def test_the_seed_csv_validates_and_stages_with_its_real_counts(dataset_env):
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        staged = data_manager.stage_upload(
            connection,
            token,
            _seed_payload(),
            "UCI_Credit_Card.csv",
            quarantine_dir=dataset_env["quarantine"],
        )
        version = staged.version
        active = data_manager.active_version(connection, token)
        row = _row(connection, "SELECT * FROM dataset_versions WHERE id = ?", (version.id,))
        actions = [
            r["action"]
            for r in connection.execute("SELECT action FROM audit_events ORDER BY id")
        ]
    finally:
        connection.close()

    assert staged.duplicate is False
    assert version.record_count == SEED_ROWS
    assert version.column_count == SEED_COLUMNS
    assert version.class_zero == SEED_CLASS_ZERO
    assert version.class_one == SEED_CLASS_ONE
    assert version.sha256 == SEED_SHA256
    assert version.status == data_manager.STATUS_VALIDATED
    # Staged, not deployed: the model keeps its own dataset until something explicitly changes.
    assert version.is_active is False
    assert active is None, "staging must not activate anything"
    assert version.validated_at and version.activated_at is None
    assert row["uploaded_by"] == _user_id(dataset_env["db"], ADMIN_USERNAME)
    # The stored copy carries a generated name, not the uploaded one.
    assert version.quarantined_filename and version.quarantined_filename.endswith(".csv")
    assert version.quarantined_filename != "UCI_Credit_Card.csv"
    assert (Path(dataset_env["quarantine"]) / version.quarantined_filename).is_file()
    assert "dataset.staged" in actions

    # The preview is aggregates only — one row per column, no record.
    preview = staged.preview
    assert preview is not None
    assert preview.record_count == SEED_ROWS
    assert preview.class_zero == SEED_CLASS_ZERO and preview.class_one == SEED_CLASS_ONE
    assert len(preview.columns) == SEED_COLUMNS
    age = next(column for column in preview.columns if column.name == "AGE")
    assert (age.minimum, age.maximum) == (21, 79)
    assert not hasattr(preview, "records")


# ------------------------------------------- 2. two malformed uploads, reasons quoted back
def test_a_missing_column_upload_is_rejected_with_the_reason_recorded(dataset_env):
    frame = _frame_from_seed(rows=50).drop(columns=["PAY_6"])
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        with pytest.raises(data_manager.DatasetRejected) as raised:
            data_manager.stage_upload(
                connection, token, _csv_bytes(frame), "missing_pay6.csv",
                quarantine_dir=dataset_env["quarantine"],
            )
        rejections = data_manager.list_rejections(connection, token)
        versions = data_manager.list_versions(connection, token)
        actions = [
            r["action"]
            for r in connection.execute("SELECT action FROM audit_events ORDER BY id")
        ]
        staged_copies = list(Path(dataset_env["quarantine"]).glob("*.csv"))
    finally:
        connection.close()

    rejection = raised.value
    assert "missing_column" in rejection.report.codes
    assert rejection.reason.startswith("missing required column(s): PAY_6;")
    assert "missing required column(s): PAY_6" in rejection.reason
    # The reason is persisted with the rejection, and no version was created from it.
    assert len(rejections) == 1
    assert rejections[0]["error_codes"] == "missing_column"
    assert rejections[0]["reason"] == rejection.reason
    assert rejections[0]["original_filename_safe"] == "missing_pay6.csv"
    assert versions == []
    assert "dataset.rejected" in actions
    # The quarantined copy of a rejected upload is removed once recorded.
    assert staged_copies == []


def test_a_wrong_target_upload_is_rejected_with_the_reason_recorded(dataset_env):
    frame = _frame_from_seed(rows=50)
    frame["default.payment.next.month"] = 2  # not a documented class
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        with pytest.raises(data_manager.DatasetRejected) as raised:
            data_manager.stage_upload(
                connection, token, _csv_bytes(frame), "wrong_target.csv",
                quarantine_dir=dataset_env["quarantine"],
            )
        rejections = data_manager.list_rejections(connection, token)
        versions = data_manager.list_versions(connection, token)
    finally:
        connection.close()

    assert raised.value.report.codes == {"invalid_target_value"}
    assert "value(s) other than 0 or 1" in raised.value.reason
    assert len(rejections) == 1 and rejections[0]["error_codes"] == "invalid_target_value"
    assert versions == []


# --------------------------- 3. the pointer persists, the artifact hash does not move
def test_the_active_pointer_persists_across_a_restart_and_the_artifact_is_unchanged(dataset_env):
    artifact_before = _sha256_of(ARTIFACT)
    manifest_before = _sha256_of(MANIFEST)

    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        seed = data_manager.ensure_seed_version(connection)
        assert seed is not None and seed.is_active
        frame = _frame_from_seed(rows=600)
        staged = data_manager.stage_upload(
            connection, token, _csv_bytes(frame), "subset_600.csv",
            quarantine_dir=dataset_env["quarantine"],
        )
        activated = data_manager.activate_version(connection, token, staged.version.id)
        assert activated.is_active
        assert activated.activated_at is not None
        assert activated.status == data_manager.STATUS_ACTIVATED
        active_before_restart = data_manager.active_version(connection, token)
    finally:
        connection.close()

    # "Restart": close the connection, open the same database file again, re-read the pointer.
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        active_after_restart = data_manager.active_version(connection, token)
        rows = connection.execute(
            "SELECT id, is_active, status FROM dataset_versions ORDER BY id"
        ).fetchall()
        assert data_manager.ensure_seed_version(connection) is not None  # startup is idempotent
        active_after_second_start = data_manager.active_version(connection, token)
        count = connection.execute("SELECT COUNT(*) AS n FROM dataset_versions").fetchone()["n"]
    finally:
        connection.close()

    assert active_after_restart is not None
    assert active_after_restart.id == active_before_restart.id == staged.version.id
    assert active_after_restart.sha256 == hashlib.sha256(_csv_bytes(frame)).hexdigest()
    assert active_after_second_start.id == staged.version.id, "a restart must not re-seed the pointer"
    assert [row["is_active"] for row in rows].count(1) == 1
    assert count == 2, "the seed must be registered exactly once"

    # The deployed artifact is byte-identical: an upload and an activation do not rebuild it.
    assert _sha256_of(ARTIFACT) == artifact_before
    assert _sha256_of(MANIFEST) == manifest_before


def test_an_upload_and_activation_never_train_or_replace_the_model(dataset_env):
    before = {
        name: _sha256_of(path) for name, path in (("artifact", ARTIFACT), ("manifest", MANIFEST))
    }
    mtimes = {path: path.stat().st_mtime_ns for path in (ARTIFACT, MANIFEST)}
    models_before = sorted(p.name for p in MODELS_DIR.iterdir())

    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        data_manager.ensure_seed_version(connection)
        staged = data_manager.stage_upload(
            connection, token, _csv_bytes(_frame_from_seed(rows=300)), "subset_300.csv",
            quarantine_dir=dataset_env["quarantine"],
        )
        data_manager.activate_version(connection, token, staged.version.id)
        audit_rows = {
            row["action"]: row["non_sensitive_details"]
            for row in connection.execute(
                "SELECT action, non_sensitive_details FROM audit_events "
                "WHERE action IN ('dataset.staged', 'dataset.activated')"
            )
        }
        comparison = data_manager.comparison(connection, token)
    finally:
        connection.close()

    assert {name: _sha256_of(path) for name, path in
            (("artifact", ARTIFACT), ("manifest", MANIFEST))} == before
    assert {path: path.stat().st_mtime_ns for path in (ARTIFACT, MANIFEST)} == mtimes
    assert sorted(p.name for p in MODELS_DIR.iterdir()) == models_before
    assert '"retraining_triggered":false' in audit_rows["dataset.staged"]
    assert '"retraining_triggered":false' in audit_rows["dataset.activated"]
    # And the page's own verdict: the active pointer is no longer the deployed dataset.
    assert comparison["active_built_the_model"] is False
    assert comparison["deployed"]["dataset_sha256"] == SEED_SHA256

    # There is no training entry point in the dataset manager at all: no import reaches the
    # training or serialisation modules, and nothing here fits or saves a model.
    source = (SRC_DIR / "data_manager.py").read_text(encoding="utf-8")
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert not [line for line in imports if "ml.train" in line or "joblib" in line
                or "pickle" in line], imports
    for forbidden in ("fit(", "predict(", ".dump(", "train_model", "load_verified_pipeline"):
        assert forbidden not in source, forbidden


# --------------------------------------------------------- 4. exactly one active version
def test_exactly_one_active_dataset_version_survives_every_activation(dataset_env):
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        seed = data_manager.ensure_seed_version(connection)
        staged = data_manager.stage_upload(
            connection, token, _csv_bytes(_frame_from_seed(rows=120)), "subset_120.csv",
            quarantine_dir=dataset_env["quarantine"],
        )

        active_ids = []

        def _active_ids() -> list[int]:
            return [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM dataset_versions WHERE is_active = 1"
                )
            ]

        data_manager.activate_version(connection, token, staged.version.id)
        active_ids.append(_active_ids())
        data_manager.activate_version(connection, token, seed.id)
        active_ids.append(_active_ids())
        data_manager.activate_version(connection, token, staged.version.id)
        active_ids.append(_active_ids())
        # Activating the already-active version is a no-op, not a second pointer.
        data_manager.activate_version(connection, token, staged.version.id)
        active_ids.append(_active_ids())

        # The database refuses a second active row even if the service is bypassed.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE dataset_versions SET is_active = 1")
    finally:
        connection.close()

    assert active_ids == [[staged.version.id], [seed.id], [staged.version.id],
                          [staged.version.id]]


def test_uploading_the_same_bytes_twice_does_not_create_a_second_version(dataset_env):
    payload = _csv_bytes(_frame_from_seed(rows=80))
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        first = data_manager.stage_upload(
            connection, token, payload, "same.csv", quarantine_dir=dataset_env["quarantine"]
        )
        second = data_manager.stage_upload(
            connection, token, payload, "same_again.csv",
            quarantine_dir=dataset_env["quarantine"],
        )
        count = connection.execute("SELECT COUNT(*) AS n FROM dataset_versions").fetchone()["n"]
        copies = list(Path(dataset_env["quarantine"]).glob("*.csv"))
    finally:
        connection.close()

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.version.id == first.version.id
    assert count == 1
    assert len(copies) == 1, "the redundant second copy is removed"


# ------------------------------------------------------- 5. a user cannot reach any of it
@pytest.mark.parametrize(
    "call",
    [
        lambda conn, token: data_manager.list_versions(conn, token),
        lambda conn, token: data_manager.active_version(conn, token),
        lambda conn, token: data_manager.list_rejections(conn, token),
        lambda conn, token: data_manager.comparison(conn, token),
        lambda conn, token: data_manager.stage_upload(
            conn, token, b"ID,LIMIT_BAL\n1,2\n", "tiny.csv"
        ),
        lambda conn, token: data_manager.activate_version(conn, token, 1),
    ],
    ids=[
        "list_versions",
        "active_version",
        "list_rejections",
        "comparison",
        "stage_upload",
        "activate_version",
    ],
)
def test_a_user_calling_a_dataset_function_is_denied_and_the_attempt_is_audited(dataset_env, call):
    connection = _open(dataset_env)
    try:
        _, token = security.login(connection, USER_USERNAME, USER_PASSWORD)
        with pytest.raises(PermissionDenied):
            call(connection, token)
        denied = connection.execute(
            "SELECT non_sensitive_details FROM audit_events WHERE action = 'auth.denied'"
        ).fetchall()
    finally:
        connection.close()

    assert denied, "a denied dataset call must be audited"
    assert any('"required":"admin"' in row["non_sensitive_details"] for row in denied)


def test_a_user_does_not_see_the_dataset_manager_entry(dataset_env):
    signed_in = _sign_in(_app(), USER_USERNAME, USER_PASSWORD)
    assert not signed_in.exception
    options = [option for option in signed_in.sidebar.radio[0].options]
    assert SECTION_DATASETS not in options
    assert SECTION_DATASETS not in _rendered(signed_in)


# ------------------------------------------------------------------------- 6. the page
def test_the_page_separates_the_deployed_dataset_from_the_staged_one(dataset_env):
    at = _dataset_page()
    assert not at.exception
    rendered = _rendered(at)

    assert "### Dataset manager" in [m.value for m in at.markdown]
    assert "Deployed model dataset vs active dataset" in rendered
    assert "In service — the deployed model" in rendered
    assert "Pointer — the active dataset version" in rendered
    # The deployed model's own dataset checksum is on screen, and it matches the artifact.
    assert SEED_SHA256 in rendered
    assert "The active dataset version is the same bytes as the dataset that built the" in rendered
    assert "Uploading does not retrain anything." in rendered
    assert "A staged dataset is validated metadata" in rendered
    assert "No upload has been rejected." in rendered
    # The seed registered at startup is the active version and is listed as such.
    assert "UCI_Credit_Card.csv" in rendered
    assert "dataset.seeded" not in rendered


def test_the_page_stages_an_upload_and_shows_counts_but_no_row(dataset_env):
    frame = _frame_from_seed(rows=400)
    payload = _csv_bytes(frame)
    expected_ones = int((frame["default.payment.next.month"] == 1).sum())
    expected_zeros = int((frame["default.payment.next.month"] == 0).sum())

    at = _dataset_page()
    at = _stage(at, "four_hundred.csv", payload)
    assert not at.exception
    rendered = _rendered(at)

    assert "Staged as dataset version" in rendered
    assert "class 0 (no default)" in rendered and str(expected_zeros) in rendered
    assert "class 1 (default)" in rendered and str(expected_ones) in rendered
    assert "Aggregate preview (no rows)" in rendered
    assert "No row of the uploaded file is rendered" in rendered
    assert expected_ones > 0 and expected_ones < len(frame)

    # The table the page rendered for the preview is per-column aggregates, not records.
    preview_columns = [
        [str(column) for column in element.value.columns]
        for element in at.dataframe
        if "distinct values" in [str(column) for column in element.value.columns]
    ]
    assert preview_columns
    assert [str(c) for c in preview_columns[0]] == [
        "column", "role", "unit", "distinct values", "min", "max", "mean",
    ]

    connection = _open(dataset_env)
    try:
        stored = connection.execute(
            "SELECT record_count, class_zero, class_one, is_active, status "
            "FROM dataset_versions WHERE record_count = ?", (len(frame),)
        ).fetchall()
    finally:
        connection.close()
    assert len(stored) == 1
    assert stored[0]["class_zero"] == expected_zeros and stored[0]["class_one"] == expected_ones
    assert stored[0]["is_active"] == 0 and stored[0]["status"] == data_manager.STATUS_VALIDATED


def test_the_page_activation_button_moves_the_pointer_and_says_the_model_is_unchanged(dataset_env):
    # Stage a valid subset of the seed directly (the UI path is covered above).
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        staged = data_manager.stage_upload(
            connection, token, _csv_bytes(_frame_from_seed(rows=200)), "subset_200.csv",
            quarantine_dir=dataset_env["quarantine"],
        )
        version_id = staged.version.id
    finally:
        connection.close()

    at = _dataset_page()
    labels = [button.label for button in at.button]
    activation = [label for label in labels if label.startswith(f"Activate dataset #{version_id}")]
    assert activation, f"no activation button for version {version_id}; labels were {labels}"
    at = _click(at, activation[0])

    assert not at.exception
    rendered = _rendered(at)
    assert f"Dataset version **#{version_id}** is now the active pointer" in rendered
    assert "The deployed model is unchanged and was not retrained." in rendered
    # The page now states the two datasets differ — which is the truth after an activation.
    assert "is **not** the dataset that built the deployed model" in rendered

    connection = _open(dataset_env)
    try:
        active = connection.execute(
            "SELECT id FROM dataset_versions WHERE is_active = 1"
        ).fetchall()
        count = connection.execute("SELECT COUNT(*) AS n FROM dataset_versions").fetchone()["n"]
    finally:
        connection.close()
    assert [row["id"] for row in active] == [version_id]
    assert count == 2


def test_the_page_lists_a_rejection_with_the_reason_it_was_refused(dataset_env):
    frame = _frame_from_seed(rows=30).drop(columns=["PAY_6"])
    connection = _open(dataset_env)
    try:
        token = _admin_token_conn(connection)
        with pytest.raises(data_manager.DatasetRejected) as raised:
            data_manager.stage_upload(
                connection, token, _csv_bytes(frame), "missing_pay6.csv",
                quarantine_dir=dataset_env["quarantine"],
            )
        reason = raised.value.reason
    finally:
        connection.close()

    at = _dataset_page()
    rendered = _rendered(at)
    assert "Rejection log" in rendered
    assert "missing_pay6.csv" in rendered
    assert "missing_column" in rendered
    assert "missing required column(s): PAY_6" in reason
    assert "missing required column(s): PAY_6" in rendered


def test_the_page_names_the_columns_it_accepts(dataset_env):
    at = _dataset_page()
    rendered = _rendered(at)
    assert "The 25-column schema this application accepts" in [
        expander.label for expander in at.expander
    ]
    schema_tables = [
        element.value
        for element in at.dataframe
        if "documented codes" in [str(column) for column in element.value.columns]
    ]
    assert schema_tables
    columns = [str(name) for name in schema_tables[0]["column"]]
    assert columns[:4] == ["ID", "LIMIT_BAL", "SEX", "EDUCATION"]
    assert "PAY_6" in columns and "default.payment.next.month" in columns
    assert len(columns) == SEED_COLUMNS
