#!/usr/bin/env python3
"""Deactivate the synthetic administrator created for the S13 tunnel journey.

Deactivation, not deletion: the account keeps its audit trail, the row stays for the record,
and the credential it was created with is useless once ``is_active = 0``. The script prints the
row afterwards so the transcript proves the state it left behind.
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, "/app")

from src import db  # noqa: E402

username = os.environ["SYNTH_ADMIN_USER"]
db_path = os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db")

connection: sqlite3.Connection = db.connect(db_path)
try:
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE username = ?",
            (moment, username),
        )
    row = connection.execute(
        "SELECT id, username, role, is_active FROM users WHERE username = ?", (username,)
    ).fetchone()
    print(f"synthetic admin deactivated: id={row['id']} username={row['username']} "
          f"role={row['role']} active={row['is_active']}")
finally:
    connection.close()
