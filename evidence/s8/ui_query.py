"""S8 evidence probe: what the administration page actually puts on screen.

Drives ``app.py`` through Streamlit's own ``AppTest`` harness against a throwaway database, then
prints the page text it can see and greps that text — plus every table cell — for the Argon2id
prefix and for the synthetic passwords the fixture used. This is the "UI query" the card asks
for: not a claim that the page is safe, but the page's own output.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from src import db, security  # noqa: E402

APP_PATH = REPO_ROOT / "app.py"
ADMIN_USERNAME = "probe_admin"
ADMIN_PASSWORD = "synthetic-admin-quartz-11"
USER_USERNAME = "probe_user"
USER_PASSWORD = "synthetic-user-anchor-22"
HASH_PREFIX = "$argon2id$"
SECTION = "User management"


def seed(connection, username: str, password: str, role: str) -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (username, username.replace("_", " ").title(), security.hash_password(password),
             role, moment, moment),
        )


def rendered(at: AppTest) -> str:
    cells = [
        str(value)
        for frame in at.dataframe
        for record in frame.value.to_dict("records")
        for value in record.values()
    ]
    return "\n".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + [s.value for s in at.success]
        + [e.value for e in at.error]
        + [w.value for w in at.warning]
        + [i.value for i in at.info]
        + cells
    )


def sign_in(username: str, password: str) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=180)
    at.run()
    at.text_input(key="login_username").set_value(username)
    at.text_input(key="login_password").set_value(password)
    return at.button[0].click().run()


def main() -> int:
    with tempfile.TemporaryDirectory() as workdir:
        path = Path(workdir) / "s8_ui.db"
        connection = db.connect(path)
        try:
            db.migrate(connection)
            seed(connection, ADMIN_USERNAME, ADMIN_PASSWORD, "admin")
            seed(connection, USER_USERNAME, USER_PASSWORD, "user")
        finally:
            connection.close()
        os.environ["APP_DB_PATH"] = str(path)

        print("== administrator: the navigation offers the section ==")
        at = sign_in(ADMIN_USERNAME, ADMIN_PASSWORD)
        assert not at.exception, at.exception
        print(f"navigation options: {at.sidebar.radio[0].options}")
        at.sidebar.radio[0].set_value(SECTION)
        at = at.run()
        assert not at.exception, at.exception

        text = rendered(at)
        print("\n== administrator: the page text (markdown/captions only) ==")
        for block in [m.value for m in at.markdown] + [c.value for c in at.caption]:
            print(f"  | {block}")

        print("\n== administrator: the accounts table as rendered ==")
        for frame in at.dataframe:
            print(f"  columns: {list(frame.value.columns)}")
            for record in frame.value.to_dict("records"):
                print(f"  row: {record}")

        print("\n== administrator: the controls on the page ==")
        print(f"  text inputs : {[i.label for i in at.text_input]}")
        print(f"  selectboxes : {[s.label for s in at.selectbox]}")
        print(f"  buttons     : {[b.label for b in at.button]}")

        print("\n== grep of everything the administrator can see ==")
        hash_hits = text.count(HASH_PREFIX)
        admin_hits = text.count(ADMIN_PASSWORD)
        user_hits = text.count(USER_PASSWORD)
        print(f"  '{HASH_PREFIX}' occurrences : {hash_hits}")
        print(f"  admin plaintext occurrences: {admin_hits}")
        print(f"  user plaintext occurrences : {user_hits}")
        print(f"  rendered characters        : {len(text)}")

        print("\n== ordinary user: the section is absent ==")
        user_at = sign_in(USER_USERNAME, USER_PASSWORD)
        assert not user_at.exception, user_at.exception
        print(f"navigation options: {user_at.sidebar.radio[0].options}")
        user_text = rendered(user_at)
        print(f"'{SECTION}' on the user's navigation: {SECTION in user_at.sidebar.radio[0].options}")
        print(f"'{SECTION}' anywhere on the user's page: {SECTION in user_text}")
        print(f"user page says why: {'not available to your role' in user_text}")

        ok = (
            hash_hits == 0
            and admin_hits == 0
            and user_hits == 0
            and SECTION in at.sidebar.radio[0].options
            and SECTION not in user_at.sidebar.radio[0].options
            and SECTION not in user_text
        )
        print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
