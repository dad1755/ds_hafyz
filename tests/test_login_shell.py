"""The Sprint 1 shell must render, and its sign-in form must not authenticate anything."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

# AppTest resolves a relative path against the calling file, so use an absolute one.
APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()
    return at


def test_shell_renders_with_the_branded_header_and_no_exception():
    at = _app()
    assert not at.exception
    assert at.title[0].value == "AI Hub Campus"
    assert at.subheader[0].value == "Credit Card Default Risk Prediction"
    assert [i.label for i in at.text_input] == ["Username", "Password"]
    assert [b.label for b in at.button] == ["Sign in"]


def test_submitting_credentials_never_authenticates():
    at = _app()
    at.text_input(key="shell_username").set_value("someone")
    at.text_input(key="shell_password").set_value("any-value-at-all")
    at.button[0].click().run()

    assert not at.exception
    # The only feedback is a warning that sign-in does not exist in this build.
    assert len(at.success) == 0
    assert len(at.error) == 0
    warnings = " ".join(w.value for w in at.warning)
    assert "not available in this build" in warnings
    # No page dispatch: the sign-in shell is still the only thing on screen.
    assert at.title[0].value == "AI Hub Campus"


def test_no_credential_echo_in_the_rendered_page():
    at = _app()
    at.text_input(key="shell_username").set_value("probe-user-xyz")
    at.text_input(key="shell_password").set_value("probe-secret-xyz")
    at.button[0].click().run()

    rendered = " ".join(
        [w.value for w in at.warning]
        + [i.value for i in at.info]
        + [c.value for c in at.caption]
        + [m.value for m in at.markdown]
    )
    assert "probe-user-xyz" not in rendered
    assert "probe-secret-xyz" not in rendered
