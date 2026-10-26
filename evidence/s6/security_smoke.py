#!/usr/bin/env python3
"""S6 behaviour demonstration against a throwaway database inside the application image.

This is a demonstration, not the test suite (that is ``tests/test_security.py``, which asserts
the same properties). It exists so the acceptance evidence contains a readable transcript of
each control firing in the real runtime, with the exception type and the message a user would
see. It never touches the operator database: it creates ``/tmp/s6_smoke.db``.

It prints no password and no session token — only exception types, public messages and
account facts.

Run inside the container:
    docker compose exec -T web python - < evidence/s6/security_smoke.py
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

sys.path.insert(0, "/app")

from src import accounts, db, security  # noqa: E402

DB = "/tmp/s6_smoke.db"
for suffix in ("", "-wal", "-shm"):
    try:
        os.unlink(DB + suffix)
    except FileNotFoundError:
        pass

ADMIN_PW = "smoke-admin-passphrase-1"
USER_PW = "smoke-user-passphrase-2"
NEW_PW = "smoke-replacement-3-ok"

conn = db.connect(DB)
print(f"database: {DB} (throwaway)")
print(f"migrations applied: {db.migrate(conn)}")


def seed(username: str, password: str, role: str, active: bool = True) -> int:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL)",
            (username, username, security.hash_password(password), role,
             1 if active else 0, moment, moment),
        )
    return int(cursor.lastrowid)


admin_id = seed("smoke_admin", ADMIN_PW, "admin")
user_id = seed("smoke_user", USER_PW, "user")
seed("smoke_off", "smoke-disabled-pass-4", "user", active=False)
print(f"seeded: admin id={admin_id}, user id={user_id}, plus one deactivated user")
stored = conn.execute("SELECT password_hash FROM users WHERE id = ?", (admin_id,)).fetchone()[0]
print(f"stored hash for smoke_admin: prefix={stored[:10]} length={len(stored)} "
      f"(the password itself is not stored anywhere)")


def show(label: str, call):
    """Run a call, print its exception type and public message, and never a token."""
    try:
        result = call()
    except security.AuthError as error:
        print(f"[{label}] {type(error).__name__}: {error.public_message}")
        return None
    print(f"[{label}] OK -> {result}")
    return result


print("\n--- 1. correct and incorrect credentials")
admin_principal, admin_token = security.login(conn, "smoke_admin", ADMIN_PW)
print(f"[admin sign-in] OK -> user_id={admin_principal.user_id} "
      f"username={admin_principal.username} role={admin_principal.role} "
      f"must_change_password={admin_principal.must_change_password} "
      f"session_expires_at={admin_principal.session_expires_at}")
token_hash_len = conn.execute("SELECT length(token_hash) FROM sessions").fetchone()[0]
print(f"    session token: {len(admin_token)} chars, stored only as a "
      f"{token_hash_len}-character sha256 digest")
show("wrong password", lambda: security.login(conn, "smoke_admin", "not-the-password"))
show("unknown username", lambda: security.login(conn, "no_such_user", "not-the-password"))
show("SQL injection attempt", lambda: security.login(
    conn, "smoke_admin' OR '1'='1", "not-the-password"))

print("\n--- 2. role guard, called directly (not through the UI)")
user_principal, user_token = security.login(conn, "smoke_user", USER_PW)
print(f"[user sign-in] OK -> username={user_principal.username} role={user_principal.role}")
show("user -> accounts.list_users", lambda: accounts.list_users(conn, user_token))
show("user -> accounts.create_user(role=admin)", lambda: accounts.create_user(
    conn, user_token, username="planted", password=NEW_PW, role="admin"))
show("user -> accounts.set_active(admin, False)", lambda: accounts.set_active(
    conn, user_token, admin_id, False))
show("no token -> accounts.list_users", lambda: accounts.list_users(conn, None))
show("admin -> accounts.list_users", lambda: [
    u.username for u in accounts.list_users(conn, admin_token)])
still_admin = conn.execute("SELECT role FROM users WHERE id = ?", (admin_id,)).fetchone()[0]
print(f"    after the denied calls, the target account's role is still '{still_admin}'")

print("\n--- 3. deactivation blocks sign-in and ends the live session")
accounts.set_active(conn, admin_token, user_id, False)
show("deactivated user sign-in", lambda: security.login(conn, "smoke_user", USER_PW))
show("deactivated user's existing token", lambda: security.resolve_session(conn, user_token))
accounts.set_active(conn, admin_token, user_id, True)
show("reactivated user sign-in", lambda: security.login(conn, "smoke_user", USER_PW)[0].username)

print("\n--- 4. the last enabled admin cannot be removed")
show("deactivate the last admin", lambda: accounts.set_active(conn, admin_token, admin_id, False))
show("demote the last admin", lambda: accounts.set_role(conn, admin_token, admin_id, "user"))
show("create a second admin, then demote the first", lambda: (
    accounts.create_user(conn, admin_token, username="smoke_admin2",
                         password="smoke-second-admin-7", role="admin").username,
    accounts.set_role(conn, admin_token, admin_id, "user").role,
))
accounts.set_role(conn, security.login(conn, "smoke_admin2", "smoke-second-admin-7")[1],
                  admin_id, "admin")  # restore for the rest of the run

print("\n--- 5. session expiry and logout")
start = db.utcnow()
_, short_token = security.login(conn, "smoke_admin", ADMIN_PW, now=start, ttl=timedelta(minutes=1))
show("token 30 s after issue", lambda: security.resolve_session(
    conn, short_token, now=start + timedelta(seconds=30)).username)
show("token 2 min after issue (expired)", lambda: security.resolve_session(
    conn, short_token, now=start + timedelta(minutes=2)))
security.logout(conn, admin_token)
show("token after logout", lambda: security.resolve_session(conn, admin_token))

print("\n--- 6. login throttle (5 failures, then the right password)")
for attempt in range(security.THROTTLE_MAX_FAILURES):
    try:
        security.login(conn, "smoke_user", "wrong", now=start + timedelta(seconds=attempt))
    except security.InvalidCredentials:
        print(f"[failure {attempt + 1}] InvalidCredentials")
show("correct password while locked", lambda: security.login(
    conn, "smoke_user", USER_PW, now=start + timedelta(seconds=10)))
show("correct password after the lock expires", lambda: security.login(
    conn, "smoke_user", USER_PW,
    now=start + security.THROTTLE_LOCKOUT + timedelta(seconds=1))[0].username)

print("\n--- 7. an admin-set temporary password forces a change")
fresh_admin_token = security.login(conn, "smoke_admin2", "smoke-second-admin-7")[1]
forced = accounts.create_user(conn, fresh_admin_token, username="smoke_forced",
                              password="smoke-initial-pass-8", role="user")
accounts.reset_password(conn, fresh_admin_token, forced.id, "smoke-temp-pass-5")
forced_token = security.login(conn, "smoke_forced", "smoke-temp-pass-5")[1]
show("forced account -> privileged call", lambda: security.require_authenticated(conn, forced_token))
show("forced account -> weak new password", lambda: security.change_password(
    conn, forced_token, "smoke-temp-pass-5", "short"))
show("forced account -> compliant new password", lambda: security.change_password(
    conn, forced_token, "smoke-temp-pass-5", "smoke-final-passphrase-6").must_change_password)
show("forced account -> after the change", lambda: security.require_authenticated(
    conn, forced_token).username)

print("\n--- 8. audit trail (no credentials in it)")
for row in conn.execute(
    "SELECT id, action, actor_user_id, non_sensitive_details FROM audit_events ORDER BY id"
):
    print(f"  #{row[0]} {row[1]} actor={row[2]} {row[3]}")

blob = "\n".join(
    str(value)
    for table in ("users", "sessions", "login_attempts", "audit_events")
    for row in conn.execute(f"SELECT * FROM {table}")
    for value in row
    if value is not None
)
leaks = [label for label, secret in (
    ("admin password", ADMIN_PW), ("user password", USER_PW), ("new password", NEW_PW),
    ("session token", admin_token)) if secret in blob]
print(f"\nplaintext search across every column of every table: "
      f"{'LEAK FOUND: ' + ', '.join(leaks) if leaks else 'none found'}")

conn.close()
sys.exit(0)
