"""Seed one disposable account into a throwaway database for the S7 browser check.

The credentials are synthetic and come from the environment of a container that is deleted
after the check. Nothing here reads, prints or stores a real credential.
"""

from __future__ import annotations

import os
import sys

from src import db, security


def main() -> int:
    path = os.environ["APP_DB_PATH"]
    username = os.environ["SYNTH_UI_USER"]
    password = os.environ["SYNTH_UI_PASSWORD"]

    conn = db.connect(path)
    try:
        applied = db.migrate(conn)
        moment = db.to_iso(db.utcnow())
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                "must_change_password, created_at, updated_at, last_login_at) "
                "VALUES (?, ?, ?, 'user', 1, 0, ?, ?, NULL)",
                (username, "S7 browser check", security.hash_password(password), moment, moment),
            )
    finally:
        conn.close()

    print(f"seeded disposable account {username!r}; schema versions applied: {applied or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
