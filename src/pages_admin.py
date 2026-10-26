"""Administration — user management (blueprint §6 routes; §9 SPRINT 8).

The page is a thin view over :mod:`src.accounts`. It holds no authorisation logic of its own:
every read and every write it calls re-checks the admin role against the database inside the
service function, so bypassing this page — calling ``accounts.create_user`` with a user's
session token — still raises ``PermissionDenied`` and still writes an ``auth.denied`` audit
row. The ``if`` statements here choose what to draw; they are not the control.

What the page deliberately does not offer:

* **No delete.** An account is deactivated instead. The audit trail and the prediction rows
  that reference the account stay intact, and a deactivated account cannot sign in.
* **No self-registration.** Accounts exist only because an administrator created one here.
* **No hash, ever.** :class:`src.accounts.UserView` has no ``password_hash`` field, so the
  table cannot render one. A reset password is typed by the admin and never echoed back —
  not in the success message, not in the audit details.
* **No way to orphan the installation.** The last enabled administrator cannot be demoted or
  deactivated; :mod:`src.accounts` refuses inside the write transaction.

Every action leaves the page with a one-line outcome in ``st.session_state`` and then reruns,
so the table the admin sees is the table the database holds.
"""

from __future__ import annotations

import streamlit as st

from src import accounts, security

#: Outcome of the last action, shown once after the rerun that follows it.
FLASH_KEY = "admin_flash"

NO_DELETE_NOTICE = (
    "Accounts are never deleted. Deactivating an account blocks sign-in immediately, ends its "
    "open sessions and keeps its audit history and prediction rows readable to administrators."
)

GUARDRAIL_NOTICE = (
    "Guardrails: there is no self-registration, no delete, and the last enabled administrator "
    "cannot be demoted or deactivated. Password hashes are never read by this page — the list "
    "has no hash column — and a temporary password you set is never shown again."
)

PASSWORD_NOTICE = (
    "A temporary password must be at least {length} characters. It is hashed before it is "
    "stored, it is never displayed or logged, and the account must change it at its next "
    "sign-in."
).format(length=security.MIN_PASSWORD_LENGTH)


def _guard(conn, token: str | None):
    """Server-side role check for this page. Returns ``None`` when the caller may not be here."""
    try:
        return security.require_role(conn, token, ("admin",), action="pages_admin.render")
    except security.AuthError as error:
        st.error(error.public_message)
        return None


def _flash(message: str) -> None:
    """Remember an outcome across the rerun that follows a write."""
    st.session_state[FLASH_KEY] = message


def _show_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.success(message)


def _users(conn, token: str | None) -> list[accounts.UserView] | None:
    """The guarded list. ``None`` means the call was refused and the reason is on screen."""
    try:
        return accounts.list_users(conn, token)
    except security.AuthError as error:
        st.error(error.public_message)
        return None


def _table(users: list[accounts.UserView]) -> None:
    """The account list. Every column comes from ``UserView``, which carries no credential."""
    st.dataframe(
        [
            {
                "username": user.username,
                "display name": user.display_name,
                "role": user.role,
                "active": user.is_active,
                "must change password": user.must_change_password,
                "created (UTC)": user.created_at,
                "last sign-in (UTC)": user.last_login_at or "never",
            }
            for user in users
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        f"{len(users)} account(s). The list is read through a guarded function and has no "
        "password-hash column: a hash is never read into the page, so it cannot be rendered. "
        "On a phone, scroll the table sideways for the remaining columns."
    )


def _create_form(conn, token: str | None) -> None:
    """Create one account. The typed password is handed straight to the hashing service."""
    with st.container(border=True):
        st.markdown("#### Create an account")
        st.caption(
            "The password you type is hashed with Argon2id before it is stored and is not "
            "shown again. Passwords need at least "
            f"{security.MIN_PASSWORD_LENGTH} characters and must not be a common password."
        )
        with st.form("admin_create_user", clear_on_submit=True):
            username = st.text_input("Username", key="admin_new_username", autocomplete="off")
            display_name = st.text_input(
                "Display name (optional)", key="admin_new_display_name", autocomplete="off"
            )
            role = st.selectbox(
                "Role",
                options=accounts.ROLES,
                index=accounts.ROLES.index("user"),
                key="admin_new_role",
            )
            password = st.text_input(
                "Initial password",
                key="admin_new_password",
                type="password",
                autocomplete="new-password",
            )
            confirm = st.text_input(
                "Confirm initial password",
                key="admin_new_password_confirm",
                type="password",
                autocomplete="off",
            )
            submitted = st.form_submit_button("Create account", type="primary", width="stretch")

        if not submitted:
            return
        if password != confirm:
            st.error("The two passwords do not match.")
            return
        try:
            created = accounts.create_user(
                conn,
                token,
                username=username,
                password=password,
                display_name=display_name,
                role=role,
            )
        except security.AuthError as error:
            st.error(error.public_message)
            return
        _flash(
            f"Account **{created.username}** created with role `{created.role}`. Give the "
            "password to its owner out of band; it is not stored or shown anywhere in this "
            "application."
        )
        st.rerun()


def _manage_one(conn, token: str | None, user: accounts.UserView) -> None:
    """One account's controls: display name, role, temporary password, active flag."""
    state = "active" if user.is_active else "deactivated"
    with st.expander(f"{user.username} — {user.display_name} · {user.role} · {state}"):
        st.caption(
            f"Account #{user.id} · created {user.created_at} · "
            f"last sign-in {user.last_login_at or 'never'}"
        )

        with st.form(f"admin_display_name_{user.id}"):
            name = st.text_input(
                "Display name",
                value=user.display_name,
                key=f"admin_display_{user.id}",
                autocomplete="off",
            )
            saved = st.form_submit_button("Save display name")
        if saved:
            try:
                updated = accounts.set_display_name(conn, token, user.id, name)
            except security.AuthError as error:
                st.error(error.public_message)
            else:
                _flash(f"Display name for **{updated.username}** saved.")
                st.rerun()

        with st.form(f"admin_role_{user.id}"):
            role = st.selectbox(
                "Role",
                options=accounts.ROLES,
                index=accounts.ROLES.index(user.role),
                key=f"admin_role_select_{user.id}",
                help="An administrator can reach this page; a user cannot.",
            )
            saved = st.form_submit_button("Save role")
        if saved:
            try:
                updated = accounts.set_role(conn, token, user.id, role)
            except security.AuthError as error:
                st.error(error.public_message)
            else:
                _flash(
                    f"Role for **{updated.username}** is now `{updated.role}`; it applies to "
                    "their next request, not only their next sign-in."
                )
                st.rerun()

        with st.form(f"admin_password_{user.id}"):
            st.caption(PASSWORD_NOTICE)
            new_password = st.text_input(
                "Temporary password",
                key=f"admin_password_new_{user.id}",
                type="password",
                autocomplete="new-password",
            )
            confirm = st.text_input(
                "Confirm temporary password",
                key=f"admin_password_confirm_{user.id}",
                type="password",
                autocomplete="off",
            )
            saved = st.form_submit_button("Set temporary password")
        if saved:
            if new_password != confirm:
                st.error("The two passwords do not match.")
            else:
                try:
                    updated = accounts.reset_password(conn, token, user.id, new_password)
                except security.AuthError as error:
                    st.error(error.public_message)
                else:
                    _flash(
                        f"A temporary password was set for **{updated.username}**. It is not "
                        "shown here, and the account must change it at its next sign-in. Its "
                        "open sessions have been ended."
                    )
                    st.rerun()

        if user.is_active:
            if st.button("Deactivate account", key=f"admin_deactivate_{user.id}", width="stretch"):
                try:
                    updated = accounts.set_active(conn, token, user.id, False)
                except security.AuthError as error:
                    st.error(error.public_message)
                else:
                    _flash(
                        f"**{updated.username}** is deactivated: it can no longer sign in and "
                        "its open sessions have ended. Nothing was deleted."
                    )
                    st.rerun()
        else:
            if st.button("Reactivate account", key=f"admin_reactivate_{user.id}", width="stretch"):
                try:
                    updated = accounts.set_active(conn, token, user.id, True)
                except security.AuthError as error:
                    st.error(error.public_message)
                else:
                    _flash(f"**{updated.username}** is active again.")
                    st.rerun()


def _audit_panel(conn, token: str | None) -> None:
    """The newest audit rows, read through the guarded function."""
    st.markdown("#### Recent audit events")
    st.caption(
        "Who did what to which entity, and when. Details are filtered by key name before they "
        "are stored, so a password, a hash, a token or a submitted feature value cannot reach "
        "this table even if a caller passes one by mistake."
    )
    try:
        events = accounts.recent_audit_events(conn, token, limit=25)
    except security.AuthError as error:
        st.error(error.public_message)
        return
    if not events:
        st.info("No audit events recorded yet.")
        return
    st.dataframe(
        [
            {
                "when (UTC)": event["created_at"],
                "action": event["action"],
                "actor": event["actor_user_id"],
                "entity": f"{event['entity_type'] or ''}:{event['entity_id'] or ''}".strip(":"),
                "details": event["non_sensitive_details"],
            }
            for event in events
        ],
        width="stretch",
        hide_index=True,
    )


def render(conn, token: str | None) -> None:
    """The User management page. Re-checks the role itself before it reads anything."""
    principal = _guard(conn, token)
    if principal is None:
        return

    st.markdown("### User management")
    st.caption(GUARDRAIL_NOTICE)
    _show_flash()

    users = _users(conn, token)
    if users is None:
        return

    st.markdown("#### Accounts")
    _table(users)

    st.markdown("#### Manage an account")
    st.caption(
        "Change a display name or role, set a temporary password, or deactivate and reactivate "
        "an account. Each control writes one audited transaction."
    )
    for user in users:
        _manage_one(conn, token, user)

    st.caption(NO_DELETE_NOTICE)
    _create_form(conn, token)
    _audit_panel(conn, token)


__all__ = ["FLASH_KEY", "GUARDRAIL_NOTICE", "NO_DELETE_NOTICE", "PASSWORD_NOTICE", "render"]
