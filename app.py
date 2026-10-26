"""AI Hub Campus — Credit Card Default Risk Prediction.

Sprint 6 entry point. The page now authenticates for real: credentials are checked against
the SQLite ``users`` table, the password hash is Argon2id, the session is a server-side row
with an expiry, and every privileged read goes through a role guard that re-reads the database
(``src.accounts``) rather than trusting anything the browser holds.

What this page does *not* do: predict (S7), manage users (S8), manage datasets (S9), show the
model evaluation (S10). Those sections are named on screen so the demo is honest about the
build it is running.

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
from src import accounts, db, security
from src.config import load_settings
from src.inference import load_service

settings = load_settings()

st.set_page_config(
    page_title="AI Hub Campus — Credit Card Default Risk Prediction",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
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


def _render_login(conn) -> None:
    with st.container(border=True):
        st.markdown("#### Sign in")
        st.caption(
            "Accounts are created by the administrator — there is no self-registration. "
            "Sign-in attempts are rate-limited and recorded in the audit trail."
        )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username", autocomplete="username")
            password = st.text_input(
                "Password",
                key="login_password",
                type="password",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

        if submitted:
            try:
                principal, token = security.login(conn, username, password)
            except security.AuthError as error:
                # One message for a wrong username and a wrong password; the throttle and the
                # inactive-account message are the only distinctions, and both are deliberate.
                st.error(error.public_message)
            else:
                st.session_state["session_token"] = token
                st.session_state["signed_in_as"] = principal.username
                st.rerun()


def _render_change_password(conn, principal, token: str) -> None:
    with st.container(border=True):
        st.markdown("#### Set a new password")
        st.warning(
            "This account must set a new password before it can be used. The password it "
            "signed in with was temporary."
        )
        st.caption(
            f"Signed in as **{principal.username}**. The new password must be at least "
            f"{security.MIN_PASSWORD_LENGTH} characters and must differ from the current one."
        )
        with st.form("change_password_form", clear_on_submit=True):
            current = st.text_input(
                "Current password", key="cp_current", type="password", autocomplete="off"
            )
            new = st.text_input(
                "New password", key="cp_new", type="password", autocomplete="new-password"
            )
            confirm = st.text_input(
                "Confirm new password", key="cp_confirm", type="password", autocomplete="off"
            )
            submitted = st.form_submit_button(
                "Save password", type="primary", use_container_width=True
            )

        if submitted:
            if new != confirm:
                st.error("The two new passwords do not match.")
            else:
                try:
                    security.change_password(conn, token, current, new)
                except security.AuthError as error:
                    st.error(error.public_message)
                else:
                    st.success("Password changed. Your other sessions have been signed out.")
                    st.rerun()

        if st.button("Sign out instead", use_container_width=True):
            security.logout(conn, token)
            st.session_state.pop("session_token", None)
            st.rerun()


def _render_signed_in(conn, principal, token: str) -> None:
    left, right = st.columns([3, 1], vertical_alignment="center")
    left.markdown(
        f"#### Signed in as **{principal.display_name}**  \n"
        f"Role `{principal.role}` · session ends {principal.session_expires_at:%Y-%m-%d %H:%M} UTC"
    )
    if right.button("Sign out", use_container_width=True):
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
        "every privileged function.\n"
        "- **Sprint 7** — the 23-field prediction form and *My History*.\n"
        "- **Sprint 8** — administrator user management (create, deactivate, reset password).\n"
        "- **Sprint 9** — dataset manager.\n"
        "- **Sprint 10** — model evaluation and EDA panels."
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
                    use_container_width=True,
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
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.caption(
            "Administration (accounts, datasets, model evaluation) is not available to your "
            "role. The server refuses those calls even if the page were bypassed."
        )


# --------------------------------------------------------------------------- page body
st.title("AI Hub Campus")
st.subheader("Credit Card Default Risk Prediction")
st.caption(
    "Academic decision-support demonstration · historical Taiwanese credit-card data (2005) "
    "· 23 account attributes · not a real credit decision"
)

_schema_versions = _prepare_database(settings.db_path)

_connection = db.connect(settings.db_path)
try:
    _principal = _current_principal(_connection)
    if _principal is None:
        _render_login(_connection)
    elif _principal.must_change_password:
        _render_change_password(_connection, _principal, _session_token() or "")
    else:
        _render_signed_in(_connection, _principal, _session_token() or "")
finally:
    _connection.close()

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
st.caption(
    "**Disclaimer.** This is a student coursework artefact, not financial advice and not an "
    "automated credit decision. It is built on the public *Default of Credit Card Clients* "
    "dataset (UCI Machine Learning Repository, dataset 350): 30,000 pseudonymous clients of a "
    "Taiwanese bank, billing months April–September 2005, amounts in New Taiwan Dollars. The "
    "model is observational and its fairness is not established; demographic features are a "
    "known risk and are discussed in the report. Do not enter real customer data."
)
