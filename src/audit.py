"""Append-only audit trail of non-sensitive facts (blueprint §6, §9 SPRINT 6).

What is recorded: *who* (a user id), *what* (a stable action name such as ``user.deactivated``),
*which* entity (type and id) and *when*. What is never recorded: passwords, password hashes,
session tokens, cookies, the session secret, or any part of a 23-feature submission.

That rule is enforced here rather than left to callers. :func:`append` filters the ``details``
mapping by key name, so a future caller that passes ``{"password": ...}`` by mistake writes a
redaction count instead of the value, and it truncates long strings so an accidental paste
cannot turn the audit table into a copy of user input. The table has no update or delete path
in this module: an audit row, once written, is what the demo shows.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any, Mapping

from src.db import to_iso, utcnow

#: Keys whose values are never persisted, whatever the caller intended.
SENSITIVE_KEY = re.compile(
    r"(pass(word|wd|phrase)|hash|token|secret|cookie|session|authorization|credential|"
    r"api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)

#: Names that contain a sensitive word but describe state, not a credential. An explicit
#: allowlist beats weakening the pattern: ``must_change_password`` is a boolean about an
#: account, and an auditor needs it.
SAFE_KEYS = frozenset({"must_change_password"})

#: Longest string kept per detail value. Anything longer is truncated with an ellipsis.
MAX_DETAIL_LENGTH = 120

#: Scalar detail types. Everything else is recorded as its type name, never as its content.
_SCALARS = (str, int, float, bool, type(None))


def sanitise_details(details: Mapping[str, Any] | None) -> str:
    """Return a JSON object safe to store, dropping sensitive keys by name.

    ``redacted_fields`` records how many keys were dropped, so an auditor can see that a
    caller *tried* to log something sensitive without seeing what it was.
    """
    if not details:
        return "{}"

    kept: dict[str, Any] = {}
    redacted = 0
    for key, value in details.items():
        name = str(key)
        if name not in SAFE_KEYS and SENSITIVE_KEY.search(name):
            redacted += 1
            continue
        if isinstance(value, str):
            kept[name] = value if len(value) <= MAX_DETAIL_LENGTH else value[: MAX_DETAIL_LENGTH - 1] + "…"
        elif isinstance(value, _SCALARS):
            kept[name] = value
        else:
            kept[name] = f"<{type(value).__name__}>"

    if redacted:
        kept["redacted_fields"] = redacted
    # sort_keys keeps the stored JSON byte-stable for a given event, which makes the evidence
    # files comparable across runs.
    return json.dumps(kept, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def append(
    conn: sqlite3.Connection,
    *,
    action: str,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    details: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> int:
    """Insert one audit row and return its id. Runs in the caller's transaction."""
    if not action or not isinstance(action, str):
        raise ValueError("action must be a non-empty string")
    cursor = conn.execute(
        "INSERT INTO audit_events "
        "(actor_user_id, action, entity_type, entity_id, created_at, non_sensitive_details) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            actor_user_id,
            action,
            entity_type,
            None if entity_id is None else str(entity_id),
            to_iso(now or utcnow()),
            sanitise_details(details),
        ),
    )
    return int(cursor.lastrowid)


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first audit rows. Callers must have checked the admin role first."""
    if limit < 1:
        return []
    rows = conn.execute(
        "SELECT id, actor_user_id, action, entity_type, entity_id, created_at, "
        "non_sensitive_details FROM audit_events ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]
