"""AI Hub Campus — Credit Card Default Risk Prediction.

Sprint 1 baseline entry point. It renders the branded shell and a static sign-in form,
and nothing else: this build has **no authentication**, no database and no model.

The sign-in form is deliberately inert. It never reads, validates, stores, hashes or
logs what is typed into it, and it never implies that a sign-in succeeded. Real
authentication and role guards arrive in Sprint 6.
"""

from __future__ import annotations

import streamlit as st

from ml.verify_artifact import ArtifactError
from src.config import load_settings
from src.inference import load_service

settings = load_settings()

st.set_page_config(
    page_title="AI Hub Campus — Credit Card Default Risk Prediction",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------- header
st.title("AI Hub Campus")
st.subheader("Credit Card Default Risk Prediction")
st.caption(
    "Academic decision-support demonstration · historical Taiwanese credit-card data (2005) "
    "· 23 account attributes · not a real credit decision"
)

st.info(
    "**Sprint 1 baseline build.** The container, configuration and this shell are in place. "
    "Sign-in, dataset management, model training and prediction are not implemented yet — "
    "nothing on this page authenticates anyone or scores anything.",
    icon="🚧",
)

# ------------------------------------------------------------------- sign-in shell
with st.container(border=True):
    st.markdown("#### Sign in")
    st.caption("Administrator and user accounts are created in Sprint 6.")

    # Static form: the inputs are keyed but never read, so no value can be checked,
    # retained or logged. Submitting only shows the notice below.
    with st.form("static_login_form", clear_on_submit=True, enter_to_submit=False):
        st.text_input("Username", key="shell_username", autocomplete="off")
        st.text_input("Password", key="shell_password", type="password", autocomplete="off")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        st.warning(
            "Sign-in is not available in this build. Nothing was checked, and what you typed "
            "was discarded immediately — it is not stored or logged anywhere."
        )

# ---------------------------------------------------------------------- build facts
try:
    # The first call verifies models/model_manifest.json against the artifact and loads it;
    # every later call reuses that object. Nothing is trained here.
    _model = load_service()
    model_status = f"{_model.model_version} (artifact sha256 {_model.artifact_sha256[:12]}…, verified)"
except ArtifactError as _error:
    model_status = f"NOT LOADED — {_error}"

with st.expander("Build information", expanded=False):
    st.write(
        {
            "Environment": settings.app_env,
            "Public domain": settings.domain,
            "Service port": settings.port,
            "Database path": settings.db_path,
            "Log retention (days)": settings.retention_days,
            "Model": model_status,
        }
    )
    st.caption(
        "Non-secret configuration only. Credentials and the tunnel token are never read by "
        "this page and never rendered."
    )

# -------------------------------------------------------------------------- footer
st.divider()
st.caption(
    "**Disclaimer.** This is a student coursework artefact, not financial advice and not an "
    "automated credit decision. It is built on the public *Default of Credit Card Clients* "
    "dataset (UCI Machine Learning Repository, dataset 350): 30,000 pseudonymous clients of a "
    "Taiwanese bank, billing months April–September 2005, amounts in New Taiwan Dollars. The "
    "model is observational and its fairness is not established; demographic features are a "
    "known risk and are discussed in the report. Do not enter real customer data."
)
