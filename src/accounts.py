"""Guarded account administration (blueprint §6 routes; §9 SPRINT 6 item 2).

Every function here is privileged and every one of them starts by calling
:func:`src.security.require_role` with the caller's session token. That ordering is the
control, not a convention: the UI in S8 hides these operations from non-admins, but a
direct import and call — ``accounts.list_users(conn, user_token)`` — raises
:class:`~src.security.PermissionDenied` and is written to the audit trail.

The module also owns the two rules that keep the installation administrable:

* **The last enabled admin cannot be demoted or deactivated.** A workspace with no admin can
  no longer create accounts or reset a password; the check runs inside the same transaction
  as the change, so two concurrent demotions cannot both pass.
* **A password set by an admin is a temporary password.** It is stored with
  ``must_change_password = 1`` and every session of that account is revoked, so the admin
  never knows a password the user is still using.

Rows are returned as :class:`UserView`, which has no ``password_hash`` field at all. A caller
cannot accidentally render a hash because it never receives one.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src import audit, security
from src.db import to_iso, transaction, utcnow
from src.security import (
    PermissionDenied,
    PolicyViolation,
    Principal,
    WeakPassword,
)

#: Usernames are typed by an operator and appear in the audit trail; keep them boring.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
ROLES = ("admin", "user")
MAX_DISPLAY_NAME = 80


@dataclass(frozen=True)
class UserView:
    """A user as the admin UI sees it: identity and state, never credential material."""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: str
    updated_at: str
    last_login_at: str | None


def _view(row: sqlite3.Row) -> UserView:
    return UserView(
        id=int(row["id"]),
        username=row["username"],
        display_name=row["display_name"] or row["username"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        must_change_password=bool(row["must_change_password"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row["last_login_at"],
    )


_USER_COLUMNS = (
    "id, username, display_name, role, is_active, must_change_password, "
    "created_at, updated_at, last_login_at"
)


def _admin(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None, action: str
) -> Principal:
    """The guard every privileged function calls first."""
    return security.require_role(
        conn, token, ("admin",), now=now, action=action
    )


def _enabled_admin_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND is_active = 1"
    ).fetchone()
    return int(row["n"])


def _require_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (int(user_id),)
    ).fetchone()
    if row is None:
        raise PolicyViolation("No such user.")
    return row


def _validate_username(username: str) -> str:
    if not isinstance(username, str) or not USERNAME_PATTERN.match(username.strip()):
        raise PolicyViolation(
            "Username must be 3–64 characters: letters, digits, dot, dash or underscore, "
            "starting with a letter or digit."
        )
    return username.strip()


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise PolicyViolation(f"Role must be one of {', '.join(ROLES)}.")
    return role


# ------------------------------------------------------------------------- admin reads
def list_users(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None
) -> list[UserView]:
    """All accounts, ordered by username. Admin only."""
    _admin(conn, token, now=now, action="accounts.list_users")
    rows = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM users ORDER BY lower(username)"
    ).fetchall()
    return [_view(row) for row in rows]


def get_user(
    conn: sqlite3.Connection, token: str | None, user_id: int, *, now: datetime | None = None
) -> UserView:
    """One account by id. Admin only."""
    _admin(conn, token, now=now, action="accounts.get_user")
    return _view(_require_user(conn, user_id))


def recent_audit_events(
    conn: sqlite3.Connection,
    token: str | None,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> list[dict]:
    """Newest-first audit rows. Admin only; the events themselves carry no secrets."""
    _admin(conn, token, now=now, action="accounts.recent_audit_events")
    return audit.recent(conn, limit=limit)


# ------------------------------------------------------------------------ admin writes
def create_user(
    conn: sqlite3.Connection,
    token: str | None,
    *,
    username: str,
    password: str,
    display_name: str = "",
    role: str = "user",
    now: datetime | None = None,
) -> UserView:
    """Create an account. Admin only; the password is hashed, never stored or echoed."""
    actor = _admin(conn, token, now=now, action="accounts.create_user")
    moment = now or utcnow()
    name = _validate_username(username)
    _validate_role(role)
    security.assert_password_policy(password)
    if len(display_name) > MAX_DISPLAY_NAME:
        raise PolicyViolation(f"Display name must be at most {MAX_DISPLAY_NAME} characters.")

    try:
        with transaction(conn):
            cursor = conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, is_active, "
                "must_change_password, created_at, updated_at, last_login_at) "
                "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
                (
                    name,
                    display_name.strip(),
                    security.hash_password(password),
                    role,
                    to_iso(moment),
                    to_iso(moment),
                ),
            )
            user_id = int(cursor.lastrowid)
            audit.append(
                conn,
                action="user.created",
                actor_user_id=actor.user_id,
                entity_type="user",
                entity_id=user_id,
                details={"username": name, "role": role},
                now=moment,
            )
    except sqlite3.IntegrityError:
        # The unique index on lower(username) is the authority; no pre-flight SELECT, which
        # would race another writer.
        raise PolicyViolation("That username is already taken.") from None

    return _view(_require_user(conn, user_id))


def set_role(
    conn: sqlite3.Connection,
    token: str | None,
    user_id: int,
    role: str,
    *,
    now: datetime | None = None,
) -> UserView:
    """Change an account's role. Refuses to leave the installation without an admin."""
    actor = _admin(conn, token, now=now, action="accounts.set_role")
    moment = now or utcnow()
    _validate_role(role)
    target = _require_user(conn, user_id)
    previous = target["role"]

    with transaction(conn):
        # Re-count inside the write transaction so a concurrent demotion cannot slip past.
        if (
            previous == "admin"
            and role != "admin"
            and bool(target["is_active"])
            and _enabled_admin_count(conn) <= 1
        ):
            raise PolicyViolation("The last enabled administrator cannot be demoted.")
        conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (role, to_iso(moment), int(user_id)),
        )
        audit.append(
            conn,
            action="user.role_changed",
            actor_user_id=actor.user_id,
            entity_type="user",
            entity_id=int(user_id),
            details={"from": previous, "to": role},
            now=moment,
        )
    return _view(_require_user(conn, user_id))


def set_active(
    conn: sqlite3.Connection,
    token: str | None,
    user_id: int,
    is_active: bool,
    *,
    now: datetime | None = None,
) -> UserView:
    """Activate or deactivate an account. Deactivation also ends its sessions at once."""
    actor = _admin(conn, token, now=now, action="accounts.set_active")
    moment = now or utcnow()
    target = _require_user(conn, user_id)

    with transaction(conn):
        if (
            not is_active
            and target["role"] == "admin"
            and bool(target["is_active"])
            and _enabled_admin_count(conn) <= 1
        ):
            raise PolicyViolation("The last enabled administrator cannot be deactivated.")
        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if is_active else 0, to_iso(moment), int(user_id)),
        )
        if not is_active:
            # Server-side sessions are rows: revoking them here is what makes deactivation
            # immediate, rather than waiting for the next sign-in.
            conn.execute(
                "UPDATE sessions SET revoked_at = ? "
                "WHERE user_id = ? AND revoked_at IS NULL",
                (to_iso(moment), int(user_id)),
            )
        audit.append(
            conn,
            action="user.activated" if is_active else "user.deactivated",
            actor_user_id=actor.user_id,
            entity_type="user",
            entity_id=int(user_id),
            details={"username": target["username"]},
            now=moment,
        )
    return _view(_require_user(conn, user_id))


def reset_password(
    conn: sqlite3.Connection,
    token: str | None,
    user_id: int,
    new_password: str,
    *,
    now: datetime | None = None,
) -> UserView:
    """Set a temporary password for an account; the user must change it at next sign-in."""
    actor = _admin(conn, token, now=now, action="accounts.reset_password")
    moment = now or utcnow()
    target = _require_user(conn, user_id)
    security.assert_password_policy(new_password)

    with transaction(conn):
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = ? "
            "WHERE id = ?",
            (security.hash_password(new_password), to_iso(moment), int(user_id)),
        )
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (to_iso(moment), int(user_id)),
        )
        audit.append(
            conn,
            action="password.reset",
            actor_user_id=actor.user_id,
            entity_type="user",
            entity_id=int(user_id),
            details={"username": target["username"], "forced_change": True},
            now=moment,
        )
    return _view(_require_user(conn, user_id))


__all__ = [
    "ROLES",
    "UserView",
    "WeakPassword",
    "create_user",
    "get_user",
    "list_users",
    "recent_audit_events",
    "reset_password",
    "set_active",
    "set_role",
]
