"""Sprint 7 UI gate: the vertical slice, driven through the real page.

Streamlit's ``AppTest`` executes ``app.py`` exactly as the server does, so these tests exercise
the same code path a browser does — sign-in, navigation, the 23 widgets, submission, the result
panel and the history page — against a temporary SQLite file and the shipped model artifact.

What each test is allowed to claim:

* the class and probability on screen are compared with ``load_service().predict(...)`` for the
  same 23 values, so "the UI shows the real model output" is measured, not asserted;
* an invalid submission produces a readable error and leaves ``prediction_logs`` untouched;
* a second identical submission does not add a row;
* one account's history never contains another account's row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ml.schema import FEATURES
from src import db, security
from src.inference import load_service
from src.pages_prediction import DEMO_EXAMPLE, FORM_GROUPS

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

USER_A = ("ui_user_a", "cobalt-lantern-heron-71")
USER_B = ("ui_user_b", "marble-orchid-vane-52")


def _seed(conn: sqlite3.Connection, username: str, password: str, role: str = "user") -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (username, username.replace("_", " ").title(), security.hash_password(password),
             role, moment, moment),
        )


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    connection = db.connect(path)
    try:
        db.migrate(connection)
        _seed(connection, *USER_A)
        _seed(connection, *USER_B)
    finally:
        connection.close()
    return path


@pytest.fixture(scope="module")
def service():
    return load_service()


def _sign_in(username: str, password: str) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    at.text_input(key="login_username").set_value(username)
    at.text_input(key="login_password").set_value(password)
    return at.button[0].click().run()


def _predict_page(username: str = USER_A[0], password: str = USER_A[1]) -> AppTest:
    at = _sign_in(username, password)
    at.sidebar.radio[0].set_value("Predict default risk")
    return at.run()


def _history_page(username: str, password: str) -> AppTest:
    at = _sign_in(username, password)
    at.sidebar.radio[0].set_value("My prediction history")
    return at.run()


def _submit(at: AppTest) -> AppTest:
    """Click the form's submit button (the demo button sits above it)."""
    labels = [b.label for b in at.button]
    return at.button[labels.index("Predict default risk")].click().run()


def _rendered(at: AppTest) -> str:
    return " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [s.value for s in at.success]
        + [e.value for e in at.error]
        + [w.value for w in at.warning]
        + [i.value for i in at.info]
    )


def _rows(path: Path) -> int:
    connection = db.connect(path)
    try:
        return int(connection.execute("SELECT COUNT(*) AS n FROM prediction_logs").fetchone()["n"])
    finally:
        connection.close()


def _history_rows(at: AppTest) -> list[dict]:
    return [dict(row) for frame in at.dataframe for row in frame.value.to_dict("records")]


def test_the_form_offers_exactly_the_23_contract_features(app_db):
    at = _predict_page()

    assert not at.exception
    keys = [widget.key for widget in at.number_input] + [widget.key for widget in at.selectbox]
    assert sorted(keys) == sorted(f"pf_{name}" for name in FEATURES)
    assert len(keys) == 23
    assert [len(names) for _, _, names in FORM_GROUPS] == [5, 6, 6, 6]
    assert "pf_PAY_1" not in keys
    assert [expander.label for expander in at.expander][:4] == [
        "1 · Credit profile — 5 inputs",
        "2 · Repayment history — 6 inputs",
        "3 · Billing amounts — 6 inputs",
        "4 · Previous paid amounts — 6 inputs",
    ]


def test_the_on_screen_result_equals_the_direct_pipeline_output(app_db, service):
    at = _predict_page()
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    at = _submit(at)

    assert not at.exception
    expected = service.predict(DEMO_EXAMPLE)

    rendered = _rendered(at)
    assert f"#### {expected.class_label}" in [m.value for m in at.markdown]
    assert (
        f"{expected.probability_label}: **{expected.probability:.2%}** "
        "*(estimated, uncalibrated)*"
    ) in [m.value for m in at.markdown]
    assert f"**Risk band: {expected.tier_label}**" in [m.value for m in at.markdown]
    assert f"model version {expected.model_version}" in rendered
    assert expected.class_caveat in rendered
    assert expected.tier_advice in rendered
    assert expected.calibration_note in rendered
    assert expected.disclaimer in rendered

    # The stored row carries the same numbers the screen showed.
    connection = db.connect(app_db)
    try:
        row = connection.execute("SELECT * FROM prediction_logs").fetchone()
    finally:
        connection.close()
    assert row["predicted_class"] == expected.predicted_class
    assert row["default_probability"] == pytest.approx(expected.probability, abs=1e-12)
    assert row["risk_tier"] == expected.risk_tier
    assert row["model_version"] == expected.model_version
    assert _rows(app_db) == 1


def test_the_demonstrator_is_labelled_synthetic_and_every_field_stays_editable(app_db):
    at = _predict_page()
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()

    rendered = _rendered(at)
    assert "Synthetic demonstrator example" in rendered
    assert "not a row from the dataset" in rendered
    assert at.number_input(key="pf_AGE").value == DEMO_EXAMPLE["AGE"]

    # Editable: changing one value changes the scored request and writes its own row.
    at.number_input(key="pf_AGE").set_value(41)
    at = _submit(at)
    assert not at.exception
    assert _rows(app_db) == 1  # one row so far, and it is the edited request
    connection = db.connect(app_db)
    try:
        row = connection.execute("SELECT * FROM prediction_logs").fetchone()
    finally:
        connection.close()
    expected = service_age_41()
    assert row["default_probability"] == pytest.approx(expected, abs=1e-12)


def service_age_41() -> float:
    return load_service().predict({**DEMO_EXAMPLE, "AGE": 41}).probability


def test_invalid_input_blocks_the_model_with_a_readable_message(app_db):
    at = _predict_page()
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    at.number_input(key="pf_LIMIT_BAL").set_value(None)
    at = _submit(at)

    assert not at.exception
    assert [e.value for e in at.error] == ["feature 'LIMIT_BAL' has no value"]
    assert "rejected before the model was called" in _rendered(at)
    assert _rows(app_db) == 0
    assert at.markdown and "#### Predicted" not in " ".join(m.value for m in at.markdown)


def test_a_repeat_submit_does_not_write_a_second_row(app_db):
    at = _predict_page()
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    at = _submit(at)
    assert _rows(app_db) == 1

    at = _submit(at)

    assert not at.exception
    assert _rows(app_db) == 1
    assert any("was not logged a second time" in i.value for i in at.info)


def test_history_shows_only_the_signed_in_accounts_rows(app_db, service):
    at = _predict_page(*USER_A)
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    _submit(at)
    expected = service.predict(DEMO_EXAMPLE)

    own = _history_page(*USER_A)
    rows = _history_rows(own)
    assert len(rows) == 1
    assert rows[0]["estimated P(default)"] == f"{expected.probability:.2%}"
    assert rows[0]["predicted class"] == expected.class_label
    assert rows[0]["risk band"] == expected.tier_label
    assert rows[0]["model version"] == expected.model_version

    other = _history_page(*USER_B)
    assert _history_rows(other) == []
    assert "No predictions yet" in _rendered(other)
    assert f"{expected.probability:.2%}" not in _rendered(other)


def test_the_history_page_states_a_row_is_not_a_default(app_db):
    at = _predict_page()
    at.button[[b.label for b in at.button].index("Load synthetic demonstrator example")].click().run()
    _submit(at)

    rendered = _rendered(_history_page(*USER_A))
    assert "A row does not mean a customer defaulted" in rendered
    assert "your own submissions only" in rendered


def test_an_anonymous_visitor_cannot_reach_the_prediction_pages(app_db):
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()

    assert [b.label for b in at.button] == ["Sign in"]
    assert at.number_input == []
    assert at.selectbox == []
    assert at.sidebar.radio == []
    assert _rows(app_db) == 0
