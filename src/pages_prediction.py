"""The 23-feature prediction form and its result panel (blueprint §4, §5, §6; SPRINT 7).

Three things this module is careful about:

**The four documented groups, exactly 23 inputs.** :data:`FORM_GROUPS` lists the groups from
blueprint §4 and the module asserts at import that they cover ``ml.schema.FEATURES`` once each
— 5 + 6 + 6 + 6, with ``PAY_0`` and ``PAY_2…PAY_6`` and no invented ``PAY_1``. A change to
the contract therefore breaks the import instead of silently dropping an input.

**The model is called once, on validated input.** The submit handler passes the raw widget
values to :func:`src.predictions.submit_prediction`, which validates them (raising
:class:`~src.validation.ValidationError` before ``predict_proba`` is reached) and records the
result. A validation failure is rendered inline and nothing is written to
``prediction_logs``.

**A repeat submission is not a second record.** The same 23 values in the same session
resolve to the same fingerprint and the existing row is shown instead.

Every unit, billing month and code meaning shown on screen comes from
``ml.schema.COLUMN_SPECS``, so the labels cannot drift from the data contract.
"""

from __future__ import annotations

import streamlit as st

from ml.schema import (
    EDUCATION_LABELS,
    FEATURES,
    MARRIAGE_LABELS,
    PAY_STATUS_LABELS,
    SEX_LABELS,
    spec_for,
)
from src import predictions, security
from src.inference import PredictionResult
from src.validation import ValidationError

#: Blueprint §4 "UI form grouping (23 inputs)", in the documented order.
FORM_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "1 · Credit profile",
        "Five account-level attributes: credit limit and the four demographic codes.",
        ("LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE"),
    ),
    (
        "2 · Repayment history",
        "Repayment status for each of the six statement months (September 2005 back to "
        "April 2005). There is no PAY_1 in this dataset and none is asked for.",
        ("PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"),
    ),
    (
        "3 · Billing amounts",
        "Statement balance for each month, in New Taiwan Dollars. A negative balance is a "
        "valid credit balance.",
        ("BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6"),
    ),
    (
        "4 · Previous paid amounts",
        "Amount actually paid in each month, in New Taiwan Dollars. Never negative.",
        ("PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6"),
    ),
)

_GROUPED: tuple[str, ...] = tuple(name for _, _, names in FORM_GROUPS for name in names)
assert _GROUPED == FEATURES, (
    "the prediction form must offer exactly the 23 contract features, once each and in "
    f"contract order; form={_GROUPED} contract={FEATURES}"
)

#: Field captions. Kept short enough to sit above a phone-width input.
LABELS: dict[str, str] = {
    "LIMIT_BAL": "Credit limit (NTD, including supplementary cards)",
    "SEX": "Sex code",
    "EDUCATION": "Education code",
    "MARRIAGE": "Marital status code",
    "AGE": "Age (whole years)",
    "PAY_0": "PAY_0 — repayment status, Sep 2005",
    "PAY_2": "PAY_2 — repayment status, Aug 2005",
    "PAY_3": "PAY_3 — repayment status, Jul 2005",
    "PAY_4": "PAY_4 — repayment status, Jun 2005",
    "PAY_5": "PAY_5 — repayment status, May 2005",
    "PAY_6": "PAY_6 — repayment status, Apr 2005",
    "BILL_AMT1": "BILL_AMT1 — statement balance, Sep 2005 (NTD)",
    "BILL_AMT2": "BILL_AMT2 — statement balance, Aug 2005 (NTD)",
    "BILL_AMT3": "BILL_AMT3 — statement balance, Jul 2005 (NTD)",
    "BILL_AMT4": "BILL_AMT4 — statement balance, Jun 2005 (NTD)",
    "BILL_AMT5": "BILL_AMT5 — statement balance, May 2005 (NTD)",
    "BILL_AMT6": "BILL_AMT6 — statement balance, Apr 2005 (NTD)",
    "PAY_AMT1": "PAY_AMT1 — amount paid, Sep 2005 (NTD)",
    "PAY_AMT2": "PAY_AMT2 — amount paid, Aug 2005 (NTD)",
    "PAY_AMT3": "PAY_AMT3 — amount paid, Jul 2005 (NTD)",
    "PAY_AMT4": "PAY_AMT4 — amount paid, Jun 2005 (NTD)",
    "PAY_AMT5": "PAY_AMT5 — amount paid, May 2005 (NTD)",
    "PAY_AMT6": "PAY_AMT6 — amount paid, Apr 2005 (NTD)",
}
assert tuple(LABELS) == FEATURES, "every contract feature needs exactly one label"

CODE_LABELS: dict[str, dict[int, str]] = {
    "SEX": SEX_LABELS,
    "EDUCATION": EDUCATION_LABELS,
    "MARRIAGE": MARRIAGE_LABELS,
}

#: The demonstrator row. Invented round numbers, chosen to land in the middle of the score
#: range so the result panel shows a band rather than a trivial 0 % or 100 %. It is **not** a
#: row from the dataset and not a real person's account; the page says so next to the button
#: and every value stays editable.
DEMO_EXAMPLE: dict[str, int] = {
    "LIMIT_BAL": 120_000,
    "SEX": 2,
    "EDUCATION": 2,
    "MARRIAGE": 2,
    "AGE": 34,
    "PAY_0": 2,
    "PAY_2": 2,
    "PAY_3": 0,
    "PAY_4": 0,
    "PAY_5": -1,
    "PAY_6": -1,
    "BILL_AMT1": 35_000,
    "BILL_AMT2": 33_500,
    "BILL_AMT3": 30_000,
    "BILL_AMT4": 28_000,
    "BILL_AMT5": 26_500,
    "BILL_AMT6": 25_000,
    "PAY_AMT1": 2_000,
    "PAY_AMT2": 2_500,
    "PAY_AMT3": 3_000,
    "PAY_AMT4": 3_000,
    "PAY_AMT5": 3_500,
    "PAY_AMT6": 4_000,
}
assert tuple(DEMO_EXAMPLE) == FEATURES, "the demonstrator must fill all 23 features"

DEMO_NOTICE = (
    "Synthetic demonstrator example — invented numbers, not a row from the dataset and not a "
    "real customer. Every field stays editable after loading."
)

_HISTORY_KEY = "prediction_seen"
_RESULT_KEY = "last_prediction"


def _guard(conn, token: str | None):
    """Server-side session check for this page. Returns ``None`` when there is no session."""
    try:
        return security.require_authenticated(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return None


def _help_for(name: str) -> str:
    spec = spec_for(name)
    parts = [spec.description, f"Unit: {spec.unit}."]
    if spec.month:
        parts.append(f"Statement month: {spec.month}.")
    if spec.allowed is not None and name in CODE_LABELS:
        parts.append(
            "Codes: " + ", ".join(f"{code} = {label}" for code, label in sorted(CODE_LABELS[name].items())) + "."
        )
    if spec.form:
        low, high = spec.form
        parts.append(f"Accepted range: {low} to {high}.")
    return " ".join(parts)


def _widget(name: str) -> None:
    """One input, built from the contract spec for that feature."""
    spec = spec_for(name)
    key = f"pf_{name}"
    label = LABELS[name]

    if name in CODE_LABELS:
        codes = sorted(CODE_LABELS[name])
        st.selectbox(
            label,
            options=codes,
            format_func=lambda code: f"{code} — {CODE_LABELS[name][code]}",
            key=key,
            help=_help_for(name),
        )
        return

    if spec.kind == "status_code":
        codes = sorted(PAY_STATUS_LABELS)
        st.selectbox(
            label,
            options=codes,
            index=codes.index(0),
            format_func=lambda code: f"{code} — {PAY_STATUS_LABELS[code]}",
            key=key,
            help=_help_for(name),
        )
        return

    low, high = spec.form if spec.form else (spec.minimum, spec.maximum)
    st.number_input(
        label,
        step=1,
        format="%d",
        min_value=low,
        max_value=high,
        value=None,
        key=key,
        help=_help_for(name),
    )


def _collect() -> dict[str, int | None]:
    """Read the 23 widget values back, in contract order, exactly as typed."""
    return {name: st.session_state.get(f"pf_{name}") for name in FEATURES}


def render_result(result: PredictionResult, entry: predictions.PredictionEntry, created: bool) -> None:
    """The result panel: class wording, probability, band, advice and disclosures (§5.9)."""
    with st.container(border=True):
        if not created:
            st.info(
                f"This identical request was already recorded at {entry.created_at} — it was "
                "not logged a second time."
            )
        st.markdown(f"#### {result.class_label}")
        st.caption(result.class_caveat)
        st.markdown(
            f"{result.probability_label}: **{result.probability:.2%}** "
            "*(estimated, uncalibrated)*"
        )
        st.markdown(f"**Risk band: {result.tier_label}**")
        st.markdown(f"**What this suggests:** {result.tier_advice}")
        st.caption(result.tier_note)
        st.caption(result.calibration_note)
        st.caption(result.false_negative_note)
        st.caption(
            f"Decision threshold {result.threshold:.2f} · model version {result.model_version} "
            f"· recorded {entry.created_at}"
        )
        st.caption(result.disclaimer)


def render(conn, token: str | None, service) -> None:
    """The Predict page. Re-checks the session itself; the caller's check is not the control."""
    principal = _guard(conn, token)
    if principal is None:
        return

    st.markdown("### Predict default risk")
    st.caption(
        "All 23 features from the data contract, in four groups. Amounts are in New Taiwan "
        "Dollars (NTD) from the 2005 statement months shown on each field. Nothing you type "
        "is stored — only the resulting class, probability, band, model version and time."
    )

    if service is None:
        st.error(
            "The model artifact could not be verified, so no prediction can be made. The "
            "failure is recorded in the build information below."
        )
        return

    st.session_state.setdefault(_HISTORY_KEY, {})
    seen = st.session_state[_HISTORY_KEY]

    if st.button("Load synthetic demonstrator example", width="stretch"):
        for name, value in DEMO_EXAMPLE.items():
            st.session_state[f"pf_{name}"] = value
        st.rerun()
    st.caption(DEMO_NOTICE)

    with st.form("prediction_form", clear_on_submit=False):
        for index, (title, caption, names) in enumerate(FORM_GROUPS):
            with st.expander(f"{title} — {len(names)} inputs", expanded=index == 0):
                st.caption(caption)
                for name in names:
                    _widget(name)
        submitted = st.form_submit_button(
            "Predict default risk", type="primary", width="stretch"
        )

    if submitted:
        features = _collect()
        try:
            entry, created, result = predictions.submit_prediction(
                conn, token, service, features, seen=seen
            )
        except ValidationError as error:
            st.error(error.message)
            st.caption(
                "The request was rejected before the model was called: nothing was scored and "
                "nothing was recorded."
            )
        else:
            st.session_state[_RESULT_KEY] = (result, entry, created)

    last = st.session_state.get(_RESULT_KEY)
    if last is not None:
        render_result(*last)
        if st.button("Clear result", width="stretch"):
            st.session_state.pop(_RESULT_KEY, None)
            st.rerun()


__all__ = [
    "DEMO_EXAMPLE",
    "DEMO_NOTICE",
    "FORM_GROUPS",
    "LABELS",
    "render",
    "render_result",
]
