"""Sprint 7 data-layer gate: who may read a prediction row, and when a second write happens.

These tests exercise :mod:`src.predictions` directly, with no Streamlit in the way:

* an anonymous caller gets an error, not rows;
* one account's history never contains another account's row, whatever argument it passes;
* the same 23 values submitted twice in one session produce one row, and the second call
  reports ``created=False`` with the row that already exists;
* an invalid request raises :class:`~src.validation.ValidationError` *before* the model is
  called and leaves the table empty;
* the stored row and the audit event carry no submitted feature value.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from src import db, predictions, security
from src.inference import load_service
from src.pages_prediction import DEMO_EXAMPLE
from src.validation import ValidationError

USER_A = ("hist_a", "cobalt-lantern-heron-71")
USER_B = ("hist_b", "marble-orchid-vane-52")


def _seed(conn: sqlite3.Connection, username: str, password: str) -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, 'user', 1, 0, ?, ?, NULL)",
            (username, username.title(), security.hash_password(password), moment, moment),
        )


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / "history.db"
    connection = db.connect(path)
    db.migrate(connection)
    _seed(connection, *USER_A)
    _seed(connection, *USER_B)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="module")
def service():
    return load_service()


def _token(conn: sqlite3.Connection, username: str, password: str) -> str:
    _, token = security.login(conn, username, password)
    return token


def _rows(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM prediction_logs").fetchone()["n"])


def test_an_anonymous_caller_gets_an_error_not_rows(conn):
    with pytest.raises(security.SessionInvalid):
        predictions.list_predictions(conn, None)
    with pytest.raises(security.SessionInvalid):
        predictions.list_predictions(conn, "not-a-real-token")


def test_a_submission_is_recorded_against_the_signed_in_account(conn, service):
    token = _token(conn, *USER_A)
    entry, created, result = predictions.submit_prediction(
        conn, token, service, DEMO_EXAMPLE, seen={}
    )

    assert created is True
    assert entry.user_id == conn.execute(
        "SELECT id FROM users WHERE username = ?", (USER_A[0],)
    ).fetchone()["id"]
    assert entry.predicted_class == result.predicted_class
    assert entry.probability == result.probability
    assert entry.risk_tier == result.risk_tier
    assert entry.model_version == service.model_version
    assert _rows(conn) == 1


def test_the_same_request_twice_in_one_session_writes_one_row(conn, service):
    token = _token(conn, *USER_A)
    seen: dict[str, int] = {}

    first, created_first, _ = predictions.submit_prediction(
        conn, token, service, DEMO_EXAMPLE, seen=seen
    )
    second, created_second, _ = predictions.submit_prediction(
        conn, token, service, DEMO_EXAMPLE, seen=seen
    )

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    assert _rows(conn) == 1


def test_one_account_never_sees_another_accounts_rows(conn, service):
    token_a = _token(conn, *USER_A)
    token_b = _token(conn, *USER_B)

    entry_a, _, _ = predictions.submit_prediction(conn, token_a, service, DEMO_EXAMPLE, seen={})
    entry_b, _, _ = predictions.submit_prediction(
        conn, token_b, service, {**DEMO_EXAMPLE, "AGE": 51}, seen={}
    )

    rows_a = predictions.list_predictions(conn, token_a)
    rows_b = predictions.list_predictions(conn, token_b)

    assert [row.id for row in rows_a] == [entry_a.id]
    assert [row.id for row in rows_b] == [entry_b.id]
    assert all(row.user_id == entry_a.user_id for row in rows_a)
    # The history call takes no user argument at all — there is nothing to point elsewhere.
    with pytest.raises(TypeError):
        predictions.list_predictions(conn, token_a, user_id=entry_b.user_id)


class _ExplodingService:
    """A stand-in that fails the test if the model is reached at all."""

    def predict(self, features):  # pragma: no cover - the assertion is the point
        raise AssertionError("the model must not be called for an invalid request")


@pytest.mark.parametrize(
    "features",
    [
        {**DEMO_EXAMPLE, "AGE": 17},          # impossible age
        {**DEMO_EXAMPLE, "LIMIT_BAL": -5_000},  # negative credit limit
        {**DEMO_EXAMPLE, "PAY_0": 42},        # code outside the documented set
        {**DEMO_EXAMPLE, "EDUCATION": 9},     # code outside the documented set
        {**DEMO_EXAMPLE, "AGE": None},        # a missing number
        {**DEMO_EXAMPLE, "PAY_AMT1": "abc"},  # non-numeric
        {k: v for k, v in DEMO_EXAMPLE.items() if k != "BILL_AMT6"},  # a missing field
    ],
)
def test_invalid_input_blocks_the_model_and_writes_nothing(conn, features):
    token = _token(conn, *USER_A)
    with pytest.raises(ValidationError):
        predictions.submit_prediction(conn, token, _ExplodingService(), features, seen={})
    assert _rows(conn) == 0


def test_no_submitted_feature_value_is_stored_or_audited(conn, service):
    token = _token(conn, *USER_A)
    predictions.submit_prediction(conn, token, service, DEMO_EXAMPLE, seen={})

    row = dict(conn.execute("SELECT * FROM prediction_logs").fetchone())
    assert set(row) == {
        "id",
        "user_id",
        "predicted_class",
        "default_probability",
        "risk_tier",
        "model_version",
        "created_at",
    }

    event = conn.execute(
        "SELECT non_sensitive_details FROM audit_events WHERE action = 'prediction.recorded'"
    ).fetchone()
    details = json.loads(event["non_sensitive_details"])
    assert set(details) == {"predicted_class", "risk_tier", "model_version"}
    for name in DEMO_EXAMPLE:
        assert name not in event["non_sensitive_details"]


def test_the_history_survives_a_new_connection(tmp_path, service):
    path = tmp_path / "persist.db"
    first = db.connect(path)
    db.migrate(first)
    _seed(first, *USER_A)
    token = _token(first, *USER_A)
    entry, _, _ = predictions.submit_prediction(first, token, service, DEMO_EXAMPLE, seen={})
    first.close()

    second = db.connect(path)
    try:
        rows = predictions.list_predictions(second, token)
        assert [row.id for row in rows] == [entry.id]
        assert rows[0].probability == entry.probability
    finally:
        second.close()
