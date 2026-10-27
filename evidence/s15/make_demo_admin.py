#!/usr/bin/env python3
"""Create a synthetic administrator for the S15 demo rehearsal.

The operator's administrator (``ds_hafyz``) is the account a human will use on demo day, and
this sprint must not rewrite its credential. The rehearsal therefore drives the administrator
pages with an account created for the run and deactivated afterwards, exactly as the S13 tunnel
check did.

The password arrives in the environment, is hashed with the application's own
``security.hash_password`` and is never printed, logged or written anywhere.

    docker compose exec -T -e SYNTH_ADMIN_USER=... -e SYNTH_ADMIN_PASSWORD=... \\
        web python - < evidence/s15/make_demo_admin.py
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, "/app")

from src import db, security  # noqa: E402

username = os.environ["SYNTH_ADMIN_USER"]
password = os.environ["SYNTH_ADMIN_PASSWORD"]
db_path = os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db")

connection: sqlite3.Connection = db.connect(db_path)
try:
    moment = db.to_iso(db.utcnow())
    existing = connection.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    with db.transaction(connection):
        if existing is None:
            connection.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                "must_change_password, created_at, updated_at, last_login_at) "
                "VALUES (?, ?, ?, 'admin', 1, 0, ?, ?, NULL)",
                (
                    username,
                    "S15 demo rehearsal (synthetic, deactivated after the run)",
                    security.hash_password(password),
                    moment,
                    moment,
                ),
            )
            action = "created"
        else:
            connection.execute(
                "UPDATE users SET password_hash = ?, role = 'admin', is_active = 1, "
                "must_change_password = 0, updated_at = ?, last_login_at = NULL "
                "WHERE username = ?",
                (security.hash_password(password), moment, username),
            )
            action = "re-armed"
    row = connection.execute(
        "SELECT id, username, role, is_active, must_change_password FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    print(
        f"synthetic admin {action}: id={row['id']} username={row['username']} "
        f"role={row['role']} active={row['is_active']} "
        f"must_change_password={row['must_change_password']} hash_prefix=$argon2id$"
    )
finally:
    connection.close()
