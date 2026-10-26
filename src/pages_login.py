"""Sign-in and forced password change (blueprint §6, §9 SPRINT 6/7).

The page is a form over :mod:`src.security`; it holds no credential logic of its own. Three
properties are deliberate and are asserted by ``tests/test_app_auth.py``:

* a wrong username and a wrong password produce the same single message;
* nothing typed into either form is echoed back into the page;
* a session token is written to ``st.session_state`` only after the database accepted the
  credentials, and the token is never rendered.
"""

from __future__ import annotations

import streamlit as st

from src import security


def render_login(conn) -> None:
    """The sign-in form. Called only when no valid session exists."""
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
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

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


def render_change_password(conn, principal, token: str) -> None:
    """The page a temporary password lands on, and nothing else."""
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
                "Save password", type="primary", width="stretch"
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

        if st.button("Sign out instead", width="stretch"):
            security.logout(conn, token)
            st.session_state.pop("session_token", None)
            st.rerun()
