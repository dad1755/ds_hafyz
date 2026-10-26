"""Seed a throwaway database for the S8 browser check.

Two synthetic accounts, so the admin page has something to list. Credentials come from the
environment of a container that is deleted after the check; nothing here reads or prints a real
credential.
"""

from __future__ import annotations

import os
import sys

from src import db, security


def main() -> int:
    path = os.environ["APP_DB_PATH"]
    admin_user = os.environ["SYNTH_ADMIN_USER"]
    admin_password = os.environ["SYNTH_ADMIN_PASSWORD"]
    user_user = os.environ["SYNTH_UI_USER"]
    user_password = os.environ["SYNTH_UI_PASSWORD"]

    conn = db.connect(path)
    try:
        applied = db.migrate(conn)
        moment = db.to_iso(db.utcnow())
        with db.transaction(conn):
            for username, password, role, display in (
                (admin_user, admin_password, "admin", "Browser Check Admin"),
                (user_user, user_password, "user", "Browser Check User"),
            ):
                conn.execute(
                    "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                    "must_change_password, created_at, updated_at, last_login_at) "
                    "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
                    (username, display, security.hash_password(password), role, moment, moment),
                )
    finally:
        conn.close()

    print(f"seeded disposable accounts {admin_user!r} (admin) and {user_user!r} (user); "
          f"schema versions applied: {applied or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
