"""Sprint 6 gate: real authentication, server-side sessions and role guards.

The card asks for nine specific behaviours. Each has a test here, and the test is written so
that it fails if the *implementation* regresses — not merely if the UI changes:

1. correct and incorrect credentials (and the same error text for both kinds of failure);
2. the throttle after N failures, and that it expires without a reset job;
3. session expiry;
4. logout;
5. a deactivated user blocked at sign-in *and* on an existing session;
6. a role bypass blocked — by direct function call, not by hiding a page;
7. the last enabled admin cannot be deactivated or demoted;
8. no plaintext password and no hash leaks into the database, the audit trail or a message;
9. the database persists across a restart (a new process/connection sees the same rows).

Everything runs against a temporary SQLite file, never the operator's database, and no test
reads `.env` or any credential from the environment.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest

from src import accounts, audit, db, security
from src.security import (
    AccountInactive,
    InvalidCredentials,
    PasswordChangeRequired,
    PermissionDenied,
    PolicyViolation,
    SessionInvalid,
    Throttled,
    WeakPassword,
)

ADMIN_PASSWORD = "amber-quartz-heron-91"
USER_PASSWORD = "violet-anchor-lamp-27"
SECOND_PASSWORD = "copper-basalt-moth-58"


# --------------------------------------------------------------------------- fixtures
@pytest.fixture()
def conn(tmp_path):
    connection = db.connect(tmp_path / "aihubcampus.db")
    db.migrate(connection)
    yield connection
    connection.close()


def seed_user(
    connection: sqlite3.Connection,
    username: str,
    password: str,
    *,
    role: str = "user",
    is_active: bool = True,
    must_change_password: bool = False,
) -> int:
    """Insert a user the way the setup script does — hashed, never plaintext."""
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        cursor = connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                username,
                username.title(),
                security.hash_password(password),
                role,
                1 if is_active else 0,
                1 if must_change_password else 0,
                moment,
                moment,
            ),
        )
    return int(cursor.lastrowid)


@pytest.fixture()
def admin(conn):
    return seed_user(conn, "admin_one", ADMIN_PASSWORD, role="admin")


@pytest.fixture()
def user(conn):
    return seed_user(conn, "demo_user", USER_PASSWORD, role="user")


def admin_token(conn) -> str:
    _, token = security.login(conn, "admin_one", ADMIN_PASSWORD)
    return token


def user_token(conn) -> str:
    _, token = security.login(conn, "demo_user", USER_PASSWORD)
    return token


# ------------------------------------------------------- 1. correct / incorrect credentials
def test_correct_credentials_return_a_principal_and_a_session(conn, admin):
    principal, token = security.login(conn, "admin_one", ADMIN_PASSWORD)

    assert principal.user_id == admin
    assert principal.username == "admin_one"
    assert principal.role == "admin"
    assert principal.is_admin is True
    assert principal.must_change_password is False
    assert isinstance(token, str) and len(token) >= 32
    # The token is not stored: only its SHA-256 is, so a database read cannot be replayed.
    stored = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert [row["token_hash"] for row in stored] != [token]


def test_username_lookup_is_case_insensitive_but_the_password_is_not(conn, user):
    principal, _ = security.login(conn, "  DEMO_USER  ", USER_PASSWORD)
    assert principal.username == "demo_user"

    with pytest.raises(InvalidCredentials):
        security.login(conn, "demo_user", USER_PASSWORD.upper())


def test_wrong_password_is_rejected_with_a_generic_message(conn, user):
    with pytest.raises(InvalidCredentials) as wrong_password:
        security.login(conn, "demo_user", "not-the-password")
    with pytest.raises(InvalidCredentials) as unknown_user:
        security.login(conn, "no_such_account", "not-the-password")

    assert wrong_password.value.public_message == "Invalid username or password."
    # Identical text for both failures: the form cannot be used to enumerate usernames.
    assert wrong_password.value.public_message == unknown_user.value.public_message
    assert "not-the-password" not in wrong_password.value.public_message


def test_empty_or_absurd_credentials_are_rejected_without_a_traceback(conn, user):
    for username, password in (
        ("", USER_PASSWORD),
        ("   ", USER_PASSWORD),
        ("x" * 65, USER_PASSWORD),
        ("demo_user", ""),
        ("demo_user", "x" * 10_000),
    ):
        with pytest.raises(InvalidCredentials):
            security.login(conn, username, password)


def test_a_sha256_looking_hash_never_verifies(conn, user):
    """There is no bare-SHA-256 path: a foreign hash format is a failure, not a match."""
    import hashlib

    plain = "password"
    legacy = hashlib.sha256(plain.encode()).hexdigest()
    with db.transaction(conn):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = 'demo_user'", (legacy,)
        )
    assert security.verify_password(legacy, plain) is False
    with pytest.raises(InvalidCredentials):
        security.login(conn, "demo_user", plain)


def test_sql_injection_in_the_username_is_data_not_sql(conn, admin):
    with pytest.raises(InvalidCredentials):
        security.login(conn, "admin_one' OR '1'='1", ADMIN_PASSWORD)
    with pytest.raises(InvalidCredentials):
        security.login(conn, "admin_one' --", ADMIN_PASSWORD)
    # The table is intact and the real account still signs in.
    assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1
    security.login(conn, "admin_one", ADMIN_PASSWORD)


# ---------------------------------------------------------------------- 2. login throttle
def test_five_failures_lock_the_username_even_for_the_right_password(conn, admin, user):
    start = db.utcnow()
    for attempt in range(security.THROTTLE_MAX_FAILURES):
        with pytest.raises(InvalidCredentials):
            security.login(conn, "demo_user", "wrong", now=start + timedelta(seconds=attempt))

    with pytest.raises(Throttled) as locked:
        security.login(conn, "demo_user", USER_PASSWORD, now=start + timedelta(seconds=10))
    assert locked.value.retry_after_seconds > 0
    assert "minute" in locked.value.public_message

    # The lock is per username: another account is unaffected.
    security.login(conn, "admin_one", ADMIN_PASSWORD, now=start + timedelta(seconds=10))


def test_the_lock_expires_by_itself(conn, user):
    start = db.utcnow()
    for attempt in range(security.THROTTLE_MAX_FAILURES):
        with pytest.raises(InvalidCredentials):
            security.login(conn, "demo_user", "wrong", now=start)

    later = start + security.THROTTLE_LOCKOUT + timedelta(seconds=1)
    principal, _ = security.login(conn, "demo_user", USER_PASSWORD, now=later)
    assert principal.username == "demo_user"
    assert security.throttle_retry_after(conn, "demo_user", now=later) == 0


def test_a_successful_sign_in_clears_the_failure_counter(conn, user):
    start = db.utcnow()
    for _ in range(security.THROTTLE_MAX_FAILURES - 1):
        with pytest.raises(InvalidCredentials):
            security.login(conn, "demo_user", "wrong", now=start)

    security.login(conn, "demo_user", USER_PASSWORD, now=start + timedelta(seconds=1))

    # Four more failures after a success start the count again rather than finishing it.
    for _ in range(security.THROTTLE_MAX_FAILURES - 1):
        with pytest.raises(InvalidCredentials):
            security.login(conn, "demo_user", "wrong", now=start + timedelta(seconds=2))
    security.login(conn, "demo_user", USER_PASSWORD, now=start + timedelta(seconds=3))


# ----------------------------------------------------------------------- 3. session expiry
def test_a_session_expires_at_its_expiry_time(conn, user):
    start = db.utcnow()
    _, token = security.login(conn, "demo_user", USER_PASSWORD, now=start, ttl=timedelta(minutes=30))

    assert security.resolve_session(conn, token, now=start + timedelta(minutes=29)).username == "demo_user"

    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, token, now=start + timedelta(minutes=30))
    with pytest.raises(SessionInvalid):
        security.require_authenticated(conn, token, now=start + timedelta(hours=1))


def test_unknown_and_malformed_tokens_are_rejected(conn, user):
    for token in (None, "", "not-a-token", "x" * 500):
        with pytest.raises(SessionInvalid):
            security.resolve_session(conn, token)


# ------------------------------------------------------------------------------ 4. logout
def test_logout_ends_the_session_and_is_idempotent(conn, user):
    _, token = security.login(conn, "demo_user", USER_PASSWORD)
    assert security.resolve_session(conn, token).username == "demo_user"

    security.logout(conn, token)
    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, token)

    # Clicking sign-out twice must not raise.
    security.logout(conn, token)
    security.logout(conn, None)


def test_logout_revokes_only_that_session(conn, user):
    _, first = security.login(conn, "demo_user", USER_PASSWORD)
    _, second = security.login(conn, "demo_user", USER_PASSWORD)

    security.logout(conn, first)

    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, first)
    assert security.resolve_session(conn, second).username == "demo_user"


# ------------------------------------------------------------------ 5. deactivated account
def test_a_deactivated_user_cannot_sign_in(conn, admin, user):
    token = admin_token(conn)
    accounts.set_active(conn, token, user, False)

    with pytest.raises(AccountInactive):
        security.login(conn, "demo_user", USER_PASSWORD)


def test_deactivation_kills_an_existing_session_immediately(conn, admin, user):
    user_session = user_token(conn)
    assert security.resolve_session(conn, user_session).username == "demo_user"

    accounts.set_active(conn, admin_token(conn), user, False)

    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, user_session)
    with pytest.raises(SessionInvalid):
        accounts.list_users(conn, user_session)  # the role is irrelevant: the session is gone


def test_reactivation_restores_sign_in(conn, admin, user):
    token = admin_token(conn)
    accounts.set_active(conn, token, user, False)
    accounts.set_active(conn, token, user, True)

    principal, _ = security.login(conn, "demo_user", USER_PASSWORD)
    assert principal.username == "demo_user"


# --------------------------------------------------------------------- 6. role bypass
PRIVILEGED_CALLS = {
    "list_users": lambda c, t, admin_id: accounts.list_users(c, t),
    "get_user": lambda c, t, admin_id: accounts.get_user(c, t, admin_id),
    "recent_audit_events": lambda c, t, admin_id: accounts.recent_audit_events(c, t),
    "create_user": lambda c, t, admin_id: accounts.create_user(
        c, t, username="planted_admin", password=SECOND_PASSWORD, role="admin"
    ),
    "set_role": lambda c, t, admin_id: accounts.set_role(c, t, admin_id, "user"),
    "set_active": lambda c, t, admin_id: accounts.set_active(c, t, admin_id, False),
    "reset_password": lambda c, t, admin_id: accounts.reset_password(
        c, t, admin_id, SECOND_PASSWORD
    ),
}


@pytest.mark.parametrize("call_name", sorted(PRIVILEGED_CALLS))
def test_a_user_session_cannot_call_an_admin_function_directly(conn, admin, user, call_name):
    token = user_token(conn)
    before = conn.execute(
        "SELECT id, role, is_active FROM users ORDER BY id"
    ).fetchall()

    with pytest.raises(PermissionDenied):
        PRIVILEGED_CALLS[call_name](conn, token, admin)

    after = conn.execute("SELECT id, role, is_active FROM users ORDER BY id").fetchall()
    assert [tuple(row) for row in after] == [tuple(row) for row in before], (
        "a denied call must not change any account"
    )

    denied = conn.execute(
        "SELECT COUNT(*) AS n FROM audit_events WHERE action = 'auth.denied'"
    ).fetchone()["n"]
    assert denied >= 1, "a denied privileged call must be audited"


def test_no_session_is_not_an_admin(conn, admin):
    for token in (None, "", "forged-token"):
        with pytest.raises(SessionInvalid):
            accounts.list_users(conn, token)


def test_an_admin_session_can_call_the_admin_functions(conn, admin, user):
    token = admin_token(conn)
    listed = accounts.list_users(conn, token)
    assert {row.username for row in listed} == {"admin_one", "demo_user"}

    created = accounts.create_user(
        conn, token, username="third_user", password=SECOND_PASSWORD, role="user"
    )
    assert created.username == "third_user"
    assert created.role == "user"
    assert created.is_active is True


def test_the_user_view_never_carries_a_password_hash(conn, admin):
    token = admin_token(conn)
    view = accounts.get_user(conn, token, admin)
    assert not hasattr(view, "password_hash")
    assert "argon2" not in repr(view).lower()


# ------------------------------------------------------------- 7. the last enabled admin
def test_the_last_enabled_admin_cannot_be_deactivated(conn, admin):
    token = admin_token(conn)
    with pytest.raises(PolicyViolation) as refused:
        accounts.set_active(conn, token, admin, False)
    assert "last enabled administrator" in refused.value.public_message
    assert accounts.get_user(conn, token, admin).is_active is True


def test_the_last_enabled_admin_cannot_be_demoted(conn, admin):
    token = admin_token(conn)
    with pytest.raises(PolicyViolation):
        accounts.set_role(conn, token, admin, "user")
    assert accounts.get_user(conn, token, admin).role == "admin"


def test_a_second_admin_makes_the_first_removable(conn, admin):
    token = admin_token(conn)
    second = accounts.create_user(
        conn, token, username="admin_two", password=SECOND_PASSWORD, role="admin"
    )

    demoted = accounts.set_role(conn, token, admin, "user")
    assert demoted.role == "user"

    # admin_two is now the last enabled admin and is protected in turn.
    _, second_token = security.login(conn, "admin_two", SECOND_PASSWORD)
    with pytest.raises(PolicyViolation):
        accounts.set_active(conn, second_token, second.id, False)


def test_a_deactivated_admin_does_not_count_as_available(conn, admin):
    """Two admins, one deactivated: the remaining enabled admin is still protected."""
    token = admin_token(conn)
    second = accounts.create_user(
        conn, token, username="admin_two", password=SECOND_PASSWORD, role="admin"
    )
    accounts.set_active(conn, token, second.id, False)

    with pytest.raises(PolicyViolation):
        accounts.set_active(conn, token, admin, False)


# ------------------------------------------------------- 8. no plaintext and no hash leaks
def test_stored_hashes_are_argon2id_and_never_the_password(conn, admin, user):
    rows = conn.execute("SELECT username, password_hash FROM users").fetchall()
    assert rows
    for row in rows:
        assert row["password_hash"].startswith("$argon2id$")
        assert row["password_hash"] != ADMIN_PASSWORD
        assert row["password_hash"] != USER_PASSWORD
        assert len(row["password_hash"]) > 50

    # Two users with the *same* password get different hashes (random salt per hash).
    first = security.hash_password(SECOND_PASSWORD)
    second = security.hash_password(SECOND_PASSWORD)
    assert first != second
    assert security.verify_password(first, SECOND_PASSWORD)
    assert security.verify_password(second, SECOND_PASSWORD)


def test_no_plaintext_password_or_token_is_stored_anywhere(conn, admin, user):
    _, token = security.login(conn, "admin_one", ADMIN_PASSWORD)
    with pytest.raises(InvalidCredentials):
        security.login(conn, "demo_user", "wrong-password")
    accounts.list_users(conn, token)
    accounts.set_active(conn, token, user, False)

    forbidden = (ADMIN_PASSWORD, USER_PASSWORD, "wrong-password", token)
    dump: list[str] = []
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    for table in tables:
        for row in conn.execute(f"SELECT * FROM {table}"):
            dump.extend("" if value is None else str(value) for value in tuple(row))
    blob = "\n".join(dump)

    for secret in forbidden:
        assert secret not in blob


def test_audit_details_refuse_sensitive_keys(conn):
    stored = audit.sanitise_details(
        {
            "password": ADMIN_PASSWORD,
            "password_hash": "$argon2id$v=19$...",
            "session_token": "abc123",
            "note": "deactivated by admin",
            "count": 2,
        }
    )
    parsed = json.loads(stored)

    assert "note" in parsed and parsed["note"] == "deactivated by admin"
    assert parsed["count"] == 2
    assert parsed["redacted_fields"] == 3
    for secret in (ADMIN_PASSWORD, "$argon2id$", "abc123"):
        assert secret not in stored


def test_audit_keeps_account_state_keys_that_merely_contain_a_sensitive_word(conn):
    stored = audit.sanitise_details({"must_change_password": True, "username": "demo_user"})
    parsed = json.loads(stored)

    assert parsed == {"must_change_password": True, "username": "demo_user"}
    assert "redacted_fields" not in parsed


def test_audit_long_values_are_truncated(conn):
    stored = audit.sanitise_details({"note": "x" * 5_000})
    assert len(json.loads(stored)["note"]) <= audit.MAX_DETAIL_LENGTH


def test_the_audit_trail_records_sign_ins_without_credentials(conn, user):
    security.login(conn, "demo_user", USER_PASSWORD)
    with pytest.raises(InvalidCredentials):
        security.login(conn, "demo_user", "wrong")

    actions = [
        row["action"] for row in conn.execute("SELECT action FROM audit_events ORDER BY id")
    ]
    assert "login.succeeded" in actions
    assert "login.failed" in actions

    details = " ".join(
        row["non_sensitive_details"] for row in conn.execute("SELECT * FROM audit_events")
    )
    assert USER_PASSWORD not in details
    assert "wrong" not in details


def test_a_weak_password_is_refused_without_echoing_it(conn):
    with pytest.raises(WeakPassword) as weak:
        security.assert_password_policy("short")
    assert "at least 12 characters" in weak.value.public_message
    assert "short" not in weak.value.public_message

    with pytest.raises(WeakPassword):
        security.assert_password_policy("password123")  # denylisted
    with pytest.raises(WeakPassword):
        security.assert_password_policy(" padded-password ")
    security.assert_password_policy("twelve-chars-ok")


def test_an_admin_reset_forces_a_change_and_kills_the_old_session(conn, admin, user):
    user_session = user_token(conn)
    token = admin_token(conn)

    accounts.reset_password(conn, token, user, SECOND_PASSWORD)

    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, user_session)

    principal, forced_token = security.login(conn, "demo_user", SECOND_PASSWORD)
    assert principal.must_change_password is True
    with pytest.raises(PasswordChangeRequired):
        security.require_authenticated(conn, forced_token)


def test_a_forced_change_blocks_privileged_calls_until_it_is_done(conn, admin):
    forced = seed_user(conn, "forced_admin", SECOND_PASSWORD, role="admin", must_change_password=True)
    principal, token = security.login(conn, "forced_admin", SECOND_PASSWORD)
    assert principal.must_change_password is True

    with pytest.raises(PasswordChangeRequired):
        accounts.list_users(conn, token)
    with pytest.raises(PasswordChangeRequired):
        security.require_role(conn, token, ("admin",))

    updated = security.change_password(conn, token, SECOND_PASSWORD, "willow-cobalt-finch-63")
    assert updated.must_change_password is False

    assert [row.username for row in accounts.list_users(conn, token)] != []
    with pytest.raises(InvalidCredentials):
        security.login(conn, "forced_admin", SECOND_PASSWORD)


def test_a_password_change_revokes_the_account_s_other_sessions(conn, user):
    _, first = security.login(conn, "demo_user", USER_PASSWORD)
    _, second = security.login(conn, "demo_user", USER_PASSWORD)

    security.change_password(conn, second, USER_PASSWORD, "willow-cobalt-finch-63")

    with pytest.raises(SessionInvalid):
        security.resolve_session(conn, first)
    assert security.resolve_session(conn, second).username == "demo_user"


def test_a_password_change_needs_the_current_password(conn, user):
    _, token = security.login(conn, "demo_user", USER_PASSWORD)
    with pytest.raises(InvalidCredentials):
        security.change_password(conn, token, "not-the-current-one", "willow-cobalt-finch-63")


# ------------------------------------------------------------ 9. persistence and schema
def test_the_database_survives_a_restart(tmp_path):
    path = tmp_path / "restart.db"

    first = db.connect(path)
    try:
        db.migrate(first)
        seed_user(first, "persisted_admin", ADMIN_PASSWORD, role="admin")
        security.login(first, "persisted_admin", ADMIN_PASSWORD)
    finally:
        first.close()

    # A brand-new connection is what a restarted container gets.
    second = db.connect(path)
    try:
        assert db.migrate(second) == [], "migrations must not re-apply on an existing database"
        principal, _ = security.login(second, "persisted_admin", ADMIN_PASSWORD)
        assert principal.role == "admin"
        assert second.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1
        assert second.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()["n"] >= 1
        assert second.execute(
            "SELECT last_login_at FROM users WHERE username = 'persisted_admin'"
        ).fetchone()["last_login_at"] is not None
    finally:
        second.close()


def test_migrations_are_idempotent_and_ordered(conn):
    assert db.migrate(conn) == []
    assert db.applied_versions(conn) == [version for version, _ in db.MIGRATIONS]

    fresh = db.connect(":memory:")
    try:
        applied = db.migrate(fresh)
        assert applied == [version for version, _ in db.MIGRATIONS]
        assert db.migrate(fresh) == []
        assert db.pending_versions(fresh) == []
    finally:
        fresh.close()


def test_every_required_table_and_index_exists(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "users",
        "prediction_logs",
        "dataset_versions",
        "audit_events",
        "schema_migrations",
        "sessions",
        "login_attempts",
    } <= tables

    indexes = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {
        "users_username_lower_key",
        "prediction_logs_user_time",
        "dataset_versions_one_active",
        "audit_events_time",
        "sessions_user",
        "login_attempts_lookup",
    } <= indexes


def test_the_database_uses_wal_and_a_busy_timeout(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_the_schema_refuses_an_unknown_role_and_a_second_active_dataset(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                "must_change_password, created_at, updated_at) "
                "VALUES ('rogue', 'Rogue', 'x', 'superuser', 1, 0, 'now', 'now')"
            )

    with db.transaction(conn):
        conn.execute(
            "INSERT INTO dataset_versions (original_filename_safe, sha256, record_count, "
            "column_count, class_zero, class_one, status, is_active) "
            "VALUES ('seed.csv', 'aaa', 1, 1, 1, 0, 'validated', 1)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO dataset_versions (original_filename_safe, sha256, record_count, "
                "column_count, class_zero, class_one, status, is_active) "
                "VALUES ('other.csv', 'bbb', 1, 1, 1, 0, 'validated', 1)"
            )


def test_a_duplicate_username_is_refused_case_insensitively(conn, admin):
    with pytest.raises(sqlite3.IntegrityError):
        seed_user(conn, "ADMIN_ONE", SECOND_PASSWORD, role="user")


def test_the_admin_cannot_create_a_duplicate_username(conn, admin):
    token = admin_token(conn)
    with pytest.raises(PolicyViolation) as duplicate:
        accounts.create_user(conn, token, username="Admin_One", password=SECOND_PASSWORD)
    assert "already taken" in duplicate.value.public_message
