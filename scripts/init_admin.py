#!/usr/bin/env python3
"""Seed the operator accounts — once, from the environment (blueprint §6, §9 SPRINT 6 item 4).

Run this at setup time, inside the running container:

    docker compose exec web python scripts/init_admin.py

What it guarantees:

* **Only when there is no admin.** If any account with ``role = 'admin'`` exists, the script
  prints that admin's username and changes nothing — no password is ever rewritten on a
  restart, so a rotated password survives a redeploy.
* **Credentials come from the environment only.** ``INITIAL_ADMIN_USERNAME`` and
  ``INITIAL_ADMIN_PASSWORD`` (plus the optional ``INITIAL_USER_USERNAME`` /
  ``INITIAL_USER_PASSWORD`` demo pair) are read from the process environment or from
  ``--env-file``. Nothing is defaulted, generated or written back to a file.
* **No plaintext is ever printed, logged or stored.** The script reports usernames, roles, the
  hash *prefix* (``$argon2id$``) and whether a change is required — never a password, never a
  full hash.
* **A password that fails the policy is still usable once, but must be changed.** The
  operator password is deliberately weak (7 characters). Rather than silently accepting it,
  the account is seeded with ``must_change_password = 1``: the first sign-in can do nothing
  except set a compliant password. See docs/architecture.md §14 (D13).

Exit codes: 0 = seeded or already present, 1 = conflict, 2 = missing/invalid configuration.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# The script is run as `python scripts/init_admin.py`, so the repository root is not on
# sys.path by default. Put it there before importing the application package.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import audit, db, security  # noqa: E402  (import after sys.path fix)

ADMIN_USERNAME_VAR = "INITIAL_ADMIN_USERNAME"
ADMIN_PASSWORD_VAR = "INITIAL_ADMIN_PASSWORD"
USER_USERNAME_VAR = "INITIAL_USER_USERNAME"
USER_PASSWORD_VAR = "INITIAL_USER_PASSWORD"


def load_env_file(path: Path, environ: dict[str, str]) -> int:
    """Merge ``KEY=VALUE`` lines into ``environ`` without overriding what is already set.

    Returns the number of keys added. This is a deliberately small parser — no interpolation,
    no ``export`` syntax — because the real deployment passes these through ``env_file`` in
    compose and never uses this path.
    """
    added = 0
    if not path.is_file():
        raise SystemExit(f"init_admin: env file not found: {path}")
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in environ:
            environ[key] = value
            added += 1
    return added


def _existing_admin(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT username FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
    ).fetchone()
    return None if row is None else row["username"]


def _find_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, username, role, is_active FROM users WHERE lower(username) = ?",
        (username.strip().lower(),),
    ).fetchone()


def _seed(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str,
    display_name: str,
    label: str,
) -> int:
    """Insert one account. Returns 0 on success, 1 when the username is taken by another role."""
    existing = _find_username(conn, username)
    if existing is not None:
        print(
            f"{label}: already exists (username={existing['username']}, "
            f"role={existing['role']}, active={bool(existing['is_active'])}) — left unchanged"
        )
        return 0 if existing["role"] == role else 1

    problems = security.password_policy_errors(password)
    must_change = 1 if problems else 0
    password_hash = security.hash_password(password)
    moment = db.to_iso(db.utcnow())

    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, NULL)",
            (username, display_name, password_hash, role, must_change, moment, moment),
        )
        user_id = int(cursor.lastrowid)
        audit.append(
            conn,
            action="user.seeded",
            actor_user_id=None,
            entity_type="user",
            entity_id=user_id,
            details={
                "username": username,
                "role": role,
                "must_change_password": bool(must_change),
            },
            now=db.utcnow(),
        )

    print(
        f"{label}: created (username={username}, role={role}, "
        f"hash_prefix=${security.hash_algorithm(password_hash)}$, "
        f"must_change_password={'yes' if must_change else 'no'})"
    )
    if problems:
        print(f"{label}: the supplied password fails the policy ({'; '.join(problems)}); "
              "the account must set a new password at first sign-in")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", help="database path (default: APP_DB_PATH or the app default)")
    parser.add_argument(
        "--env-file",
        type=Path,
        help="optional KEY=VALUE file to read when the variables are not already exported",
    )
    args = parser.parse_args(argv)

    environ = dict(os.environ)
    if args.env_file is not None:
        added = load_env_file(args.env_file, environ)
        print(f"env: read {added} variable(s) from {args.env_file}")

    admin_username = environ.get(ADMIN_USERNAME_VAR, "").strip()
    admin_password = environ.get(ADMIN_PASSWORD_VAR, "")
    if not admin_username or not admin_password:
        print(
            f"init_admin: {ADMIN_USERNAME_VAR} and {ADMIN_PASSWORD_VAR} must be set "
            "(the values are never printed)",
            file=sys.stderr,
        )
        return 2

    db_path = db.resolve_db_path(args.db)
    conn = db.connect(db_path)
    try:
        applied = db.migrate(conn)
        print(f"db: {db_path} (migrations applied by this run: {len(applied)}"
              f"{' — ' + ', '.join(applied) if applied else ''})")

        status = 0
        if _existing_admin(conn) is not None:
            print(
                f"admin: already exists (username={_existing_admin(conn)}) — "
                "password left unchanged"
            )
        else:
            status |= _seed(
                conn,
                username=admin_username,
                password=admin_password,
                role="admin",
                display_name="Administrator",
                label="admin",
            )

        user_username = environ.get(USER_USERNAME_VAR, "").strip()
        user_password = environ.get(USER_PASSWORD_VAR, "")
        if user_username and user_password:
            status |= _seed(
                conn,
                username=user_username,
                password=user_password,
                role="user",
                display_name="Demo user",
                label="demo user",
            )
        else:
            print(f"demo user: skipped ({USER_USERNAME_VAR}/{USER_PASSWORD_VAR} not set)")

        purged = db.purge_expired_sessions(conn)
        if purged:
            print(f"sessions: purged {purged} long-expired session(s)")

        rows = conn.execute(
            "SELECT username, role, is_active, must_change_password, "
            "substr(password_hash, 1, 10) AS hash_prefix "
            "FROM users ORDER BY id"
        ).fetchall()
        print(f"accounts: {len(rows)}")
        for row in rows:
            print(
                f"  - username={row['username']} role={row['role']} "
                f"active={bool(row['is_active'])} "
                f"must_change_password={bool(row['must_change_password'])} "
                f"hash_prefix={row['hash_prefix']}"
            )
        return status
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
