"""AI Hub Campus — Credit Card Default Risk Prediction.

Sprint 7 entry point. The page authenticates for real (S6) and now serves the prediction
vertical slice: a 23-input form, the verified model's answer, and the signed-in account's own
prediction history.

Dispatch is deliberately boring: resolve the session from the database on every rerun, then
render exactly one of sign-in, forced password change, or a signed-in page. Each page module
re-checks the session itself, so the branch here is presentation rather than the control.

What this page does *not* do: manage users (S8), manage datasets (S9), show the model
evaluation (S10). Those sections are named on screen so the demo is honest about the build it
is running.

Security rules that shape the code below:

* nothing typed into a form is stored, logged or rendered — only the outcome is;
* the session token lives in ``st.session_state`` (server-side for this session) and is
  re-validated against the database on every rerun, so sign-out, expiry and deactivation take
  effect immediately;
* no password, hash or token is ever written into the page, including in the error text.
"""

from __future__ import annotations

import streamlit as st

from ml.verify_artifact import ArtifactError
from src import accounts, db, pages_history, pages_login, pages_prediction, security
from src.config import load_settings
from src.inference import load_service

FOOTER = "Academic decision-support demonstration · historical data · not a bank credit decision"

settings = load_settings()

st.set_page_config(
    page_title="AI Hub Campus — Credit Card Default Risk Prediction",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="auto",
)


@st.cache_resource
def _prepare_database(db_path: str) -> list[str]:
    """Create the schema once per process. Idempotent, so a restart changes nothing."""
    conn = db.connect(db_path)
    try:
        return db.migrate(conn)
    finally:
        conn.close()


def _session_token() -> str | None:
    token = st.session_state.get("session_token")
    return token if isinstance(token, str) and token else None


def _current_principal(conn):
    """Re-validate the session against the database on every run; never trust the page."""
    token = _session_token()
    if token is None:
        return None
    try:
        return security.resolve_session(conn, token)
    except security.AuthError:
        st.session_state.pop("session_token", None)
        return None


def _render_home(conn, principal, token: str, service) -> None:
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(
        f"#### Signed in as **{principal.display_name}**  \n"
        f"Role `{principal.role}` · session ends {principal.session_expires_at:%Y-%m-%d %H:%M} UTC"
    )
    if right.button("Sign out", width="stretch"):
        security.logout(conn, token)
        st.session_state.pop("session_token", None)
        st.rerun()

    st.success(
        "Authentication is live: your session is a server-side record, and every privileged "
        "call re-checks your role against the database.",
        icon="🔐",
    )

    st.markdown("**What this build contains**")
    st.markdown(
        "- **Available now** — sign-in, sign-out, session expiry and the role guard behind "
        "every privileged function; the 23-feature prediction form, the verified model's "
        "result and your own prediction history.\n"
        "- **Sprint 8** — administrator user management (create, deactivate, reset password).\n"
        "- **Sprint 9** — dataset manager.\n"
        "- **Sprint 10** — model evaluation and EDA panels."
    )

    st.markdown("**How to use it**")
    st.markdown(
        "Open **Predict default risk** in the sidebar, fill the four groups of the form (or "
        "load the synthetic demonstrator example first), submit, and read the result. "
        "**My prediction history** lists only the predictions your own account requested."
    )
    st.caption(
        "The model is a decision-tree pipeline trained on the historical UCI credit-card "
        "sample. It estimates the probability of default next month; it is not a credit "
        "decision and its probabilities are uncalibrated."
        + (
            f" Loaded model: `{service.model_version}`."
            if service is not None
            else " The model artifact is not loaded — see Build information below."
        )
    )

    if principal.role == "admin":
        with st.container(border=True):
            st.markdown("#### Accounts")
            try:
                # A guarded read: this function re-checks the admin role against the database
                # itself, so the `if` above is presentation, not the control.
                users = accounts.list_users(conn, token)
            except security.AuthError as error:
                st.error(error.public_message)
            else:
                st.dataframe(
                    [
                        {
                            "username": user.username,
                            "display name": user.display_name,
                            "role": user.role,
                            "active": user.is_active,
                            "must change password": user.must_change_password,
                            "last sign-in": user.last_login_at or "never",
                        }
                        for user in users
                    ],
                    width="stretch",
                    hide_index=True,
                )
                st.caption(
                    "Password hashes are never read into the page. Creating, deactivating and "
                    "resetting accounts arrives in Sprint 8."
                )

            st.markdown("##### Recent audit events")
            try:
                events = accounts.recent_audit_events(conn, token, limit=10)
            except security.AuthError as error:
                st.error(error.public_message)
            else:
                st.dataframe(
                    [
                        {
                            "when": event["created_at"],
                            "action": event["action"],
                            "actor": event["actor_user_id"],
                            "details": event["non_sensitive_details"],
                        }
                        for event in events
                    ],
                    width="stretch",
                    hide_index=True,
                )
    else:
        st.caption(
            "Administration (accounts, datasets, model evaluation) is not available to your "
            "role. The server refuses those calls even if the page were bypassed."
        )


def _navigation() -> str:
    """Sidebar navigation. Not a security boundary — every page guards itself."""
    with st.sidebar:
        st.markdown("**AI Hub Campus**")
        return st.radio(
            "Section",
            options=("Home", "Predict default risk", "My prediction history"),
            key="nav",
            label_visibility="collapsed",
        )


# --------------------------------------------------------------------------- page body
st.title("AI Hub Campus")
st.subheader("Credit Card Default Risk Prediction")
st.caption(
    "Academic decision-support demonstration · historical Taiwanese credit-card data (2005) "
    "· 23 account attributes · not a real credit decision"
)

_schema_versions = _prepare_database(settings.db_path)

try:
    # The first call verifies models/model_manifest.json against the artifact and loads it;
    # every later call reuses that object. Nothing is trained here.
    _service = load_service()
    model_status = f"{_service.model_version} (artifact sha256 {_service.artifact_sha256[:12]}…, verified)"
except ArtifactError as _error:
    _service = None
    model_status = f"NOT LOADED — {_error}"

_connection = db.connect(settings.db_path)
try:
    _principal = _current_principal(_connection)
    _token = _session_token() or ""
    if _principal is None:
        pages_login.render_login(_connection)
    elif _principal.must_change_password:
        pages_login.render_change_password(_connection, _principal, _token)
    else:
        _section = _navigation()
        if _section == "Predict default risk":
            pages_prediction.render(_connection, _token, _service)
        elif _section == "My prediction history":
            pages_history.render(_connection, _token, _service)
        else:
            _render_home(_connection, _principal, _token, _service)
finally:
    _connection.close()

# ---------------------------------------------------------------------- build facts
with st.expander("Build information", expanded=False):
    st.write(
        {
            "Environment": settings.app_env,
            "Public domain": settings.domain,
            "Service port": settings.port,
            "Database path": settings.db_path,
            "Schema versions": ", ".join(_schema_versions) or "already applied",
            "Password hashing": "Argon2id (argon2-cffi)",
            "Session lifetime (hours)": int(security.SESSION_TTL.total_seconds() // 3600),
            "Log retention (days)": settings.retention_days,
            "Model": model_status,
        }
    )
    st.caption(
        "Non-secret configuration only. Credentials, password hashes and the tunnel token are "
        "never read by this page and never rendered."
    )

# -------------------------------------------------------------------------- footer
st.divider()
st.caption(FOOTER)
st.caption(
    "**Disclaimer.** This is a student coursework artefact, not financial advice and not an "
    "automated credit decision. It is built on the public *Default of Credit Card Clients* "
    "dataset (UCI Machine Learning Repository, dataset 350): 30,000 pseudonymous clients of a "
    "Taiwanese bank, billing months April–September 2005, amounts in New Taiwan Dollars. The "
    "model is observational and its fairness is not established; demographic features are a "
    "known risk and are discussed in the report. Do not enter real customer data."
)
