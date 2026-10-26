"""Guarded prediction history and the single write path for a scored request.

Blueprint §6 ("My History") and §9 SPRINT 7. Two rules shape this module:

* **A prediction row belongs to exactly one account, and only that account can read it.**
  :func:`list_predictions` filters by the user id *resolved from the session token*, never by
  an argument, so there is no parameter a caller could supply to read someone else's rows.
  Both functions start with :func:`src.security.require_authenticated`, so an anonymous call
  raises :class:`~src.security.SessionInvalid` rather than returning data.
* **A repeated submission of the same 23 values does not create a second row.**
  :func:`submit_prediction` keeps a per-session map of request fingerprint → row id. A second
  identical request inside the same session returns the row already recorded and reports
  ``created=False``; the page shows the existing result instead of logging a duplicate.

What is stored is the *result* only — class, probability, band, model version, timestamp.
The 23 submitted values are never written to the database or to the audit trail (blueprint §6:
no raw feature snapshot), which is also why the duplicate guard is scoped to the session that
made the submission rather than to the stored rows.

Nothing here renders anything; the page modules own presentation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, MutableMapping

from src import audit, security
from src.db import to_iso, transaction, utcnow
from src.inference import PredictionResult
from src.security import Principal
from src.validation import ValidationError, validate_features

#: Newest rows kept for one page render. The history page is a personal list, not a report.
MAX_HISTORY_ROWS = 200

#: How many fingerprints one session remembers. A demo session submits a handful; the cap
#: keeps a long-lived browser session from growing without bound.
MAX_REMEMBERED_REQUESTS = 50

_ENTRY_COLUMNS = (
    "id, user_id, predicted_class, default_probability, risk_tier, model_version, created_at"
)


@dataclass(frozen=True)
class PredictionEntry:
    """One recorded prediction. It carries no submitted feature value."""

    id: int
    user_id: int
    predicted_class: int
    probability: float
    risk_tier: str
    model_version: str
    created_at: str


def _entry(row: sqlite3.Row) -> PredictionEntry:
    return PredictionEntry(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        predicted_class=int(row["predicted_class"]),
        probability=float(row["default_probability"]),
        risk_tier=row["risk_tier"],
        model_version=row["model_version"],
        created_at=row["created_at"],
    )


def _guard(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None, action: str
) -> Principal:
    """A valid session for *any* role — prediction is a user feature, not an admin one."""
    del action  # the guard is the same for both roles; the name is for the call site's clarity
    return security.require_authenticated(conn, token, now=now)


def request_fingerprint(user_id: int, features: Mapping[str, int]) -> str:
    """Stable identity of one scored request, for the duplicate-submission guard.

    Canonical JSON in contract order, so the same 23 values always hash the same and a
    reordered mapping does not look like a new request.
    """
    canonical = json.dumps(
        {"user": int(user_id), "features": {name: int(features[name]) for name in features}},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_prediction(
    conn: sqlite3.Connection,
    token: str | None,
    result: PredictionResult,
    *,
    now: datetime | None = None,
) -> PredictionEntry:
    """Insert one row for the signed-in account and return it. Audited, no feature values."""
    principal = _guard(conn, token, now=now, action="predictions.record")
    moment = now or utcnow()
    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO prediction_logs "
            "(user_id, predicted_class, default_probability, risk_tier, model_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                principal.user_id,
                int(result.predicted_class),
                float(result.probability),
                str(result.risk_tier),
                str(result.model_version),
                to_iso(moment),
            ),
        )
        entry_id = int(cursor.lastrowid)
        audit.append(
            conn,
            action="prediction.recorded",
            actor_user_id=principal.user_id,
            entity_type="prediction_log",
            entity_id=entry_id,
            details={
                "predicted_class": int(result.predicted_class),
                "risk_tier": str(result.risk_tier),
                "model_version": str(result.model_version),
            },
            now=moment,
        )
    return PredictionEntry(
        id=entry_id,
        user_id=principal.user_id,
        predicted_class=int(result.predicted_class),
        probability=float(result.probability),
        risk_tier=str(result.risk_tier),
        model_version=str(result.model_version),
        created_at=to_iso(moment),
    )


def list_predictions(
    conn: sqlite3.Connection,
    token: str | None,
    *,
    limit: int = MAX_HISTORY_ROWS,
    now: datetime | None = None,
) -> list[PredictionEntry]:
    """The signed-in account's own rows, newest first. Never another account's rows."""
    principal = _guard(conn, token, now=now, action="predictions.list")
    rows = conn.execute(
        f"SELECT {_ENTRY_COLUMNS} FROM prediction_logs "
        "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (principal.user_id, max(1, int(limit))),
    ).fetchall()
    return [_entry(row) for row in rows]


def _existing(
    conn: sqlite3.Connection, entry_id: int, user_id: int
) -> PredictionEntry | None:
    row = conn.execute(
        f"SELECT {_ENTRY_COLUMNS} FROM prediction_logs WHERE id = ? AND user_id = ?",
        (int(entry_id), int(user_id)),
    ).fetchone()
    return None if row is None else _entry(row)


def submit_prediction(
    conn: sqlite3.Connection,
    token: str | None,
    service: Any,
    features: Mapping[str, Any],
    *,
    seen: MutableMapping[str, int],
    now: datetime | None = None,
) -> tuple[PredictionEntry, bool, PredictionResult]:
    """Validate, score, then record — at most once per identical request per session.

    Returns ``(entry, created, result)``. ``created`` is ``False`` when this exact request was
    already recorded in this session, in which case nothing was written and ``entry`` is the
    row that already exists.

    Validation happens before the model is touched (``InferenceService.predict`` calls
    ``validate_features`` first), so an invalid request raises
    :class:`~src.validation.ValidationError` and leaves the log untouched.
    """
    principal = _guard(conn, token, now=now, action="predictions.submit")
    validated = validate_features(features)
    result = service.predict(validated)

    fingerprint = request_fingerprint(principal.user_id, validated)
    previous = seen.get(fingerprint)
    if previous is not None:
        entry = _existing(conn, previous, principal.user_id)
        if entry is not None:
            return entry, False, result
        seen.pop(fingerprint, None)  # the remembered row is gone; record this request

    entry = record_prediction(conn, token, result, now=now)
    seen[fingerprint] = entry.id
    while len(seen) > MAX_REMEMBERED_REQUESTS:
        seen.pop(next(iter(seen)))
    return entry, True, result


__all__ = [
    "MAX_HISTORY_ROWS",
    "MAX_REMEMBERED_REQUESTS",
    "PredictionEntry",
    "list_predictions",
    "record_prediction",
    "request_fingerprint",
    "submit_prediction",
    "ValidationError",
]
