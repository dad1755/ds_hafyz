"""S8 evidence probe: every admin write, then a sweep of the audit table for credentials.

Runs against a throwaway SQLite file. It prints audit rows (which are non-sensitive by
construction) and the result of grepping those rows — and the whole database file — for the
synthetic passwords this script used, for the Argon2id prefix, and for the stored hashes.

Nothing here reads ``.env``, the operator's database or any real credential.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import accounts, db, security  # noqa: E402

ADMIN_USERNAME = "probe_admin"
ADMIN_PASSWORD = "synthetic-admin-quartz-11"
USER_USERNAME = "probe_user"
USER_PASSWORD = "synthetic-user-anchor-22"
NEW_PASSWORD = "synthetic-temp-lantern-33"
CREATED_PASSWORD = "synthetic-created-heron-44"

HASH_PREFIX = "$argon2id$"


def seed(conn: sqlite3.Connection, username: str, password: str, role: str) -> int:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (username, username.title(), security.hash_password(password), role, moment, moment),
        )
    return int(cursor.lastrowid)


def main() -> int:
    with tempfile.TemporaryDirectory() as workdir:
        path = Path(workdir) / "s8_probe.db"
        conn = db.connect(path)
        try:
            db.migrate(conn)
            admin_id = seed(conn, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
            user_id = seed(conn, USER_USERNAME, USER_PASSWORD, "user")
            _, admin_token = security.login(conn, ADMIN_USERNAME, ADMIN_PASSWORD)
            _, user_token = security.login(conn, USER_USERNAME, USER_PASSWORD)

            print("== admin writes (each one transactional and audited) ==")
            created = accounts.create_user(
                conn,
                admin_token,
                username="probe_created",
                password=CREATED_PASSWORD,
                display_name="Probe Created",
                role="user",
            )
            print(f"create_user           -> id={created.id} username={created.username} "
                  f"role={created.role} must_change_password={created.must_change_password}")
            print(f"set_display_name      -> {accounts.set_display_name(conn, admin_token, user_id, 'Probe Renamed').display_name!r}")
            print(f"set_role (promote)    -> {accounts.set_role(conn, admin_token, user_id, 'admin').role}")
            print(f"set_role (demote)     -> {accounts.set_role(conn, admin_token, user_id, 'user').role}")
            reset = accounts.reset_password(conn, admin_token, user_id, NEW_PASSWORD)
            print(f"reset_password        -> must_change_password={reset.must_change_password}")
            print(f"set_active (deactivate)-> is_active={accounts.set_active(conn, admin_token, user_id, False).is_active}")
            print(f"set_active (reactivate)-> is_active={accounts.set_active(conn, admin_token, user_id, True).is_active}")

            print("\n== guardrails ==")
            try:
                accounts.set_role(conn, admin_token, admin_id, "user")
            except security.AuthError as error:
                print(f"demote last admin     -> refused: {type(error).__name__}: {error.public_message}")
            try:
                accounts.set_active(conn, admin_token, admin_id, False)
            except security.AuthError as error:
                print(f"deactivate last admin -> refused: {type(error).__name__}: {error.public_message}")
            try:
                accounts.create_user(conn, admin_token, username="probe_user", password=NEW_PASSWORD)
            except security.AuthError as error:
                print(f"duplicate username    -> refused: {type(error).__name__}: {error.public_message}")
            # Sign in as the freshly created ordinary account and reach for an admin function.
            # (The earlier user session was revoked by the admin's password reset, which is the
            # intended behaviour and is asserted in tests/test_admin.py.)
            _, intruder_token = security.login(conn, "probe_created", CREATED_PASSWORD)
            try:
                accounts.list_users(conn, intruder_token)
            except security.AuthError as error:
                print(f"user calls admin fn   -> refused: {type(error).__name__}: {error.public_message}")
            print(f"delete path present   -> {hasattr(accounts, 'delete_user') or hasattr(accounts, 'remove_user')}")

            print("\n== audit_events, newest last (details verbatim) ==")
            rows = conn.execute(
                "SELECT id, actor_user_id, action, entity_type, entity_id, non_sensitive_details "
                "FROM audit_events ORDER BY id"
            ).fetchall()
            for row in rows:
                print(
                    f"{row['id']:>3} actor={row['actor_user_id']} {row['action']:<26} "
                    f"{row['entity_type']}:{row['entity_id']} {row['non_sensitive_details']}"
                )
            print(f"total audit rows: {len(rows)}")

            denied = [row for row in rows if row["action"] == "auth.denied"]
            print("\n== quoted denied row ==")
            assert denied, "expected an auth.denied row"
            row = denied[-1]
            print(f"SELECT * FROM audit_events WHERE id = {row['id']};")
            for key in row.keys():
                print(f"  {key} = {row[key]!r}")

            print("\n== sweep: audit details must hold no credential ==")
            secrets = (ADMIN_PASSWORD, USER_PASSWORD, NEW_PASSWORD, CREATED_PASSWORD)
            hashes = [r["password_hash"] for r in conn.execute("SELECT password_hash FROM users")]
            findings = 0
            for row in rows:
                details = row["non_sensitive_details"]
                for secret in secrets:
                    if secret in details:
                        findings += 1
                        print(f"LEAK plaintext in audit row {row['id']} ({row['action']})")
                if HASH_PREFIX in details or "$argon2" in details:
                    findings += 1
                    print(f"LEAK hash prefix in audit row {row['id']} ({row['action']})")
                for stored in hashes:
                    if stored in details:
                        findings += 1
                        print(f"LEAK full hash in audit row {row['id']} ({row['action']})")
            print(f"grep '{HASH_PREFIX}' in audit details: {sum(HASH_PREFIX in r['non_sensitive_details'] for r in rows)} match(es)")
            print(f"grep synthetic passwords in audit details: {sum(any(s in r['non_sensitive_details'] for s in secrets) for r in rows)} match(es)")
            print(f"grep full password hashes in audit details: {sum(any(h in r['non_sensitive_details'] for h in hashes) for r in rows)} match(es)")

            print("\n== sweep: the whole database file ==")
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            raw = path.read_bytes()
            print(f"file: {path.name} ({len(raw)} bytes)")
            for secret in secrets:
                print(f"  plaintext {secret[:8]}… present: {secret.encode() in raw}")
            print(f"  Argon2id prefix present (expected — the users table stores hashes): {HASH_PREFIX.encode() in raw}")

            print("\n== what the admin API returns (no hash field) ==")
            for view in accounts.list_users(conn, admin_token):
                print(f"  {view}")
            print(f"UserView fields: {sorted(accounts.UserView.__dataclass_fields__)}")

            print(f"\nRESULT: {'PASS' if findings == 0 else 'FAIL'} — "
                  f"{len(rows)} audit rows inspected, {findings} credential finding(s)")
            return 0 if findings == 0 else 1
        finally:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
