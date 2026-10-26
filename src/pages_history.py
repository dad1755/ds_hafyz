"""My prediction history — the signed-in account's own rows only (blueprint §6; SPRINT 7).

The list comes from :func:`src.predictions.list_predictions`, which filters by the user id
resolved from the session token inside the database query. There is no page parameter, no
query-string value and no widget that can widen that filter, so one account cannot read
another's history even by calling the function directly with its own token.

What a row means is stated on the page: it is a model output that this account asked for. It
is not a record that a real customer defaulted — the dataset is a historical sample and the
model is observational.
"""

from __future__ import annotations

import streamlit as st

from src import predictions, security
from src.recommendations import TIER_BY_KEY

CLASS_WORDING: dict[int, str] = {
    0: "Predicted non-default next month",
    1: "Predicted default next month",
}

NOTICE = (
    "These are model outputs you requested, stored against your account. A row does not mean a "
    "customer defaulted: the model is an observational estimate on historical 2005 data, and "
    "its probabilities are uncalibrated."
)


def _class_wording(manifest_classes: dict[str, str] | None) -> dict[int, str]:
    """The manifest's own class wording when the artifact is loaded, else the same text."""
    if not manifest_classes:
        return dict(CLASS_WORDING)
    return {int(key): str(value) for key, value in manifest_classes.items()}


def _tier_label(key: str) -> str:
    tier = TIER_BY_KEY.get(key)
    return tier.label if tier else key


def render(conn, token: str | None, service) -> None:
    """The history page. Re-checks the session itself before reading anything."""
    try:
        principal = security.require_authenticated(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return

    st.markdown("### My prediction history")
    st.caption(NOTICE)

    try:
        rows = predictions.list_predictions(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return

    if not rows:
        st.info(
            "No predictions yet. Open **Predict default risk**, fill the 23 features and "
            "submit — the result is recorded here against your account."
        )
        return

    wording = _class_wording((service.manifest.get("classes") if service else None) or None)
    st.dataframe(
        [
            {
                "recorded (UTC)": row.created_at,
                "predicted class": wording.get(row.predicted_class, str(row.predicted_class)),
                "estimated P(default)": f"{row.probability:.2%}",
                "risk band": _tier_label(row.risk_tier),
                "model version": row.model_version,
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        f"{len(rows)} row(s) shown for **{principal.username}** — your own submissions only. "
        "No submitted feature values are stored, so a row cannot be re-scored from history. "
        "On a phone, scroll the table sideways for the remaining columns."
    )


__all__ = ["NOTICE", "render"]
