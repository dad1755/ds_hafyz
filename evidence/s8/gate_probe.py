"""S8 independent gate probe — run by the reviewing agent, not the implementer.

Proves, against a throwaway database, the three things the card says an auditor must be able to
see for themselves:

1. every privileged service function refuses a non-admin caller **and** writes a row to
   ``audit_events`` naming the attempt (row quoted verbatim);
2. the last enabled administrator cannot be demoted or deactivated, from the service layer;
3. no password hash and no plaintext password exists in anything the administrator can see
   (the rendered page), in ``audit_events``, or anywhere in the database file's SQL dump.

Output is plain text on stdout; the gate run captures it to evidence/s8/gate_probe.txt.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

#: The page reads its database from this variable; set it before Streamlit loads app.py.
_GATE_TMP = Path(tempfile.mkdtemp(prefix="s8gate-"))
os.environ["APP_DB_PATH"] = str(_GATE_TMP / "gate.db")

from streamlit.testing.v1 import AppTest  # noqa: E402

from src import accounts, db, security
from src.security import PermissionDenied, PolicyViolation

APP_PATH = Path(__file__).resolve().parents[2] / "app.py"

ADMIN = "gate_admin"
ADMIN_PW = "granite-harbour-vane-42"
USER = "gate_user"
USER_PW = "juniper-lantern-reed-77"
NEW_PW = "obsidian-meadow-crane-19"
TEMP_PW = "thistle-copper-marsh-64"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def seed(conn: sqlite3.Connection, username: str, password: str, role: str) -> int:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (username, username, security.hash_password(password), role, moment, moment),
        )
    return int(cur.lastrowid)


def rendered(at: AppTest) -> str:
    cells = [
        str(value)
        for frame in at.dataframe
        for record in frame.value.to_dict("records")
        for value in record.values()
    ]
    return " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [s.value for s in at.success]
        + [e.value for e in at.error]
        + [w.value for w in at.warning]
        + [i.value for i in at.info]
        + cells
    )


def main() -> int:
    tmp = _GATE_TMP
    path = _GATE_TMP / "gate.db"
    conn = db.connect(path)
    db.migrate(conn)
    admin_id = seed(conn, ADMIN, ADMIN_PW, "admin")
    user_id = seed(conn, USER, USER_PW, "user")

    print("=" * 78)
    print("S8 GATE PROBE — independent re-run by the reviewing agent")
    print("=" * 78)

    # ---------------------------------------------------------------- 1. denied + audited
    print("\n1. A non-admin session calling each privileged function (direct import, no UI)")
    _, user_token = security.login(conn, USER, USER_PW)
    calls = {
        "list_users": lambda: accounts.list_users(conn, user_token),
        "get_user": lambda: accounts.get_user(conn, user_token, admin_id),
        "create_user": lambda: accounts.create_user(
            conn, user_token, username="planted_admin", password=NEW_PW, role="admin"
        ),
        "set_display_name": lambda: accounts.set_display_name(conn, user_token, admin_id, "Owned"),
        "set_role": lambda: accounts.set_role(conn, user_token, admin_id, "user"),
        "set_active": lambda: accounts.set_active(conn, user_token, admin_id, False),
        "reset_password": lambda: accounts.reset_password(conn, user_token, admin_id, NEW_PW),
        "recent_audit_events": lambda: accounts.recent_audit_events(conn, user_token),
    }
    before = [tuple(r) for r in conn.execute("SELECT id, role, is_active FROM users ORDER BY id")]
    for name, call in calls.items():
        try:
            call()
            check(f"{name} refused for a user session", False, "call SUCCEEDED")
        except PermissionDenied:
            denied_row = conn.execute(
                "SELECT id, actor_user_id, action, entity_type, entity_id, non_sensitive_details "
                "FROM audit_events WHERE action='auth.denied' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            check(
                f"{name} refused for a user session",
                denied_row is not None
                and f'"attempted":"accounts.{name}"' in denied_row["non_sensitive_details"],
                "audited as auth.denied",
            )
    after = [tuple(r) for r in conn.execute("SELECT id, role, is_active FROM users ORDER BY id")]
    check("a denied call changes no account", before == after)

    quoted = conn.execute(
        "SELECT * FROM audit_events WHERE action='auth.denied' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    print("\n   Quoted audit_events row for a denied attempt:")
    for key in quoted.keys():
        print(f"     {key:<22} = {quoted[key]!r}")

    # ---------------------------------------------------------------- 2. last-admin guard
    print("\n2. Last enabled administrator cannot be orphaned")
    _, admin_token = security.login(conn, ADMIN, ADMIN_PW)
    for label, call in {
        "demote last admin": lambda: accounts.set_role(conn, admin_token, admin_id, "user"),
        "deactivate last admin": lambda: accounts.set_active(conn, admin_token, admin_id, False),
    }.items():
        try:
            call()
            check(label, False, "SUCCEEDED")
        except PolicyViolation as error:
            check(label, True, f"refused: {error}")
    still = conn.execute("SELECT role, is_active FROM users WHERE id=?", (admin_id,)).fetchone()
    check("admin still admin and active", still["role"] == "admin" and bool(still["is_active"]))

    # ---------------------------------------------------------------- 3. admin writes
    print("\n3. Admin writes through the service layer")
    created = accounts.create_user(
        conn, admin_token, username="gate_created", password=NEW_PW, display_name="Gate Created"
    )
    accounts.set_display_name(conn, admin_token, user_id, "Renamed By Gate")
    accounts.set_role(conn, admin_token, user_id, "admin")
    accounts.set_role(conn, admin_token, user_id, "user")
    accounts.reset_password(conn, admin_token, user_id, TEMP_PW)
    accounts.set_active(conn, admin_token, user_id, False)
    accounts.set_active(conn, admin_token, user_id, True)
    check("created account exists", created.username == "gate_created")
    check(
        "no delete path on the accounts module",
        not any(hasattr(accounts, n) for n in ("delete_user", "remove_user", "purge_user")),
    )

    print("\n   audit_events written by the admin actions:")
    for row in conn.execute(
        "SELECT id, actor_user_id, action, entity_type, entity_id, non_sensitive_details "
        "FROM audit_events ORDER BY id"
    ):
        print(
            f"     {row['id']:>3} actor={row['actor_user_id']} {row['action']:<26} "
            f"{row['entity_type']}:{row['entity_id']} {row['non_sensitive_details']}"
        )

    # ---------------------------------------------------------------- 4. credential sweep
    print("\n4. Credential sweep")
    secrets = (ADMIN_PW, USER_PW, NEW_PW, TEMP_PW)
    hashes = [r["password_hash"] for r in conn.execute("SELECT password_hash FROM users")]
    audit_blob = "\n".join(
        f"{r['action']} {r['non_sensitive_details']}"
        for r in conn.execute("SELECT action, non_sensitive_details FROM audit_events")
    )
    check("no '$argon2' prefix in audit_events", "$argon2" not in audit_blob)
    check("no plaintext password in audit_events", not any(s in audit_blob for s in secrets))
    check("no stored hash in audit_events", not any(h in audit_blob for h in hashes))

    dump = "\n".join(conn.iterdump())
    check("no plaintext password anywhere in the SQL dump", not any(s in dump for s in secrets))
    check(
        "hash appears only in users.password_hash",
        dump.count("$argon2id$") == len(hashes),
        f"{dump.count('$argon2id$')} hash literal(s) for {len(hashes)} account(s)",
    )
    conn.close()

    # ---------------------------------------------------------------- 5. rendered page
    print("\n5. The page's own output, rendered through AppTest against this database")
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    at.text_input(key="login_username").set_value(ADMIN)
    at.text_input(key="login_password").set_value(ADMIN_PW)
    at.button[0].click().run()
    at.sidebar.radio[0].set_value("User management")
    at.run()
    text = rendered(at)
    check("admin page rendered without exception", not at.exception, repr(at.exception)[:120])
    check("accounts table present", "#### Accounts" in [m.value for m in at.markdown])
    columns = [str(c) for frame in at.dataframe for c in frame.value.columns]
    print(f"   table columns: {columns[:7]}")
    check("no hash column", not any("hash" in c for c in columns))
    check("no '$argon2' in anything on screen", "$argon2" not in text)
    check("no plaintext password on screen", not any(s in text for s in secrets))
    check("no stored hash on screen", not any(h in text for h in hashes))
    check("no delete button on screen", not any("Delete" in b.label for b in at.button))
    print(f"   rendered characters: {len(text)}")

    # ------------------------------------------------- 6. the acceptance clause end to end
    print("\n6. Acceptance clause: an admin provisions a user in the page, who then signs in")
    ui_password = "meridian-quartz-tide-31"
    at.text_input(key="admin_new_username").set_value("gate_ui_user")
    at.text_input(key="admin_new_display_name").set_value("Gate UI User")
    at.text_input(key="admin_new_password").set_value(ui_password)
    at.text_input(key="admin_new_password_confirm").set_value(ui_password)
    create_buttons = [b for b in at.button if b.label == "Create account"]
    check("the page offers a Create account button", bool(create_buttons))
    at = create_buttons[0].click().run()
    flash = rendered(at)
    check("no exception after creating an account in the page", not at.exception, repr(at.exception)[:120])
    check("the page confirms the account was created", "gate_ui_user" in flash and "created" in flash)
    check("the typed password is not echoed back", ui_password not in flash)
    check("no hash in the confirmation", "$argon2" not in flash)

    probe = db.connect(path)
    try:
        principal, token = security.login(probe, "gate_ui_user", ui_password)
        check("the account created in the page signs in", principal.username == "gate_ui_user")
        check("the new account starts as a plain user", principal.role == "user")
        try:
            accounts.list_users(probe, token)
            check("the new account cannot reach admin functions", False, "SUCCEEDED")
        except PermissionDenied:
            check("the new account cannot reach admin functions", True, "refused")
        row = probe.execute(
            "SELECT action, non_sensitive_details FROM audit_events WHERE action='user.created' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        print(f"   user.created row: {row['action']} {row['non_sensitive_details']}")
        check("the creation is audited without a credential", ui_password not in row["non_sensitive_details"])
    finally:
        probe.close()

    # --------------------------------------------------- 7. final sweep after every write
    print("\n7. Final credential sweep over the finished database")
    final = db.connect(path)
    try:
        final_secrets = secrets + (ui_password,)
        final_hashes = [r["password_hash"] for r in final.execute("SELECT password_hash FROM users")]
        final_audit = "\n".join(
            f"{r['action']} {r['non_sensitive_details']}"
            for r in final.execute("SELECT action, non_sensitive_details FROM audit_events")
        )
        final_dump = "\n".join(final.iterdump())
        check("no plaintext in audit_events", not any(s in final_audit for s in final_secrets))
        check("no plaintext anywhere in the SQL dump", not any(s in final_dump for s in final_secrets))
        check("no hash in audit_events", not any(h in final_audit for h in final_hashes))
        check(
            "each account's hash appears exactly once in the dump",
            all(final_dump.count(h) == 1 for h in final_hashes),
            f"{len(final_hashes)} accounts",
        )
        check("every write produced an audit row", final.execute("SELECT COUNT(*) c FROM audit_events").fetchone()["c"] >= 20)
    finally:
        final.close()

    print("\n" + "=" * 78)
    if failures:
        print(f"RESULT: FAIL — {len(failures)} check(s) failed: {failures}")
        return 1
    print("RESULT: PASS — every gate check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
