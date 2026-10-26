#!/usr/bin/env python3
"""Read-only inspection of the running app's database, for the S6 evidence files.

Prints structure and *derived* facts only: pragmas as the application sets them, table names,
row counts, and for each account its username, role, flags, the hash **prefix**, the hash
length and a SHA-256 digest of the hash string (which proves the stored value did not change
across a restart without disclosing it). No password, no full hash and no session token is
printed.

Run inside the container:
    docker compose exec -T web python - < evidence/s6/inspect_db.py
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, "/app")

from src import db  # noqa: E402  (the app's own connection, so the pragmas are the real ones)

path = db.resolve_db_path(os.environ.get("APP_DB_PATH"))
print(f"db_path            : {path}")
print(f"db_size_bytes      : {os.path.getsize(path)}")

conn = db.connect(path)
conn.row_factory = None  # plain tuples are fine here; keeps the output narrow

print(f"journal_mode       : {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
print(f"busy_timeout_ms    : {conn.execute('PRAGMA busy_timeout').fetchone()[0]}")
print(f"foreign_keys       : {conn.execute('PRAGMA foreign_keys').fetchone()[0]}")

print("\nschema_migrations:")
for version, applied_at in conn.execute(
    "SELECT version, applied_at FROM schema_migrations ORDER BY version"
):
    print(f"  {version}  applied_at={applied_at}")

print("\ntables (rows):")
for (name,) in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
):
    count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"  {name:18s} {count}")

print("\naccounts (no hash, no password — prefix, length and a digest of the hash only):")
for row in conn.execute(
    "SELECT username, role, is_active, must_change_password, password_hash, "
    "last_login_at FROM users ORDER BY id"
):
    username, role, is_active, must_change, stored, last_login = row
    digest = hashlib.sha256(stored.encode()).hexdigest()[:16]
    print(
        f"  username={username:12s} role={role:5s} active={bool(is_active)!s:5s} "
        f"must_change_password={bool(must_change)!s:5s} hash_prefix={stored[:10]} "
        f"hash_len={len(stored)} sha256(hash)={digest} last_login_at={last_login}"
    )

print("\naudit_events (last 8):")
for row in conn.execute(
    "SELECT id, action, actor_user_id, created_at, non_sensitive_details "
    "FROM audit_events ORDER BY id DESC LIMIT 8"
):
    print(f"  #{row[0]} {row[3]} action={row[1]} actor={row[2]} details={row[4]}")

print("\nsessions:")
for row in conn.execute(
    "SELECT user_id, created_at, expires_at, revoked_at, length(token_hash) "
    "FROM sessions ORDER BY created_at"
):
    print(
        f"  user_id={row[0]} created={row[1]} expires={row[2]} revoked={row[3]} "
        f"token_hash_len={row[4]}"
    )

conn.close()
sys.exit(0)
