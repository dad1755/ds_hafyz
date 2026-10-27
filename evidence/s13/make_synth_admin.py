#!/usr/bin/env python3
"""Create a synthetic administrator for the S13 tunnel journey.

The operator's own administrator (``ds_hafyz``) is seeded with
``must_change_password = 1`` by design (docs/architecture.md D13), so its first sign-in can only
reach the "set a new password" screen. Driving the administrator *pages* through the tunnel
therefore needs an account that is already usable — and it must not be the operator's, whose
credential this project is forbidden to rewrite.

This script inserts one synthetic admin into the live database. The password arrives in the
environment, is hashed with the application's own ``security.hash_password`` and is never
printed, logged or written anywhere. The account is deactivated afterwards by
``deactivate_synth_admin.py``.

    docker compose exec -T -e SYNTH_ADMIN_USER=... -e SYNTH_ADMIN_PASSWORD=... \
        web python /work/make_synth_admin.py
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
                    "S13 tunnel check (synthetic, deactivated after the run)",
                    security.hash_password(password),
                    moment,
                    moment,
                ),
            )
            action = "created"
        else:
            # A previous run left the account behind, deactivated. Re-arm it with a fresh
            # password rather than failing on the unique index.
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
    print(f"synthetic admin {action}: id={row['id']} username={row['username']} "
          f"role={row['role']} active={row['is_active']} "
          f"must_change_password={row['must_change_password']} hash_prefix=$argon2id$")
finally:
    connection.close()
