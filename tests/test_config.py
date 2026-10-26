"""Sprint 1 smoke test: the settings loader defaults, overrides and rejects bad input."""

from __future__ import annotations

import pytest

from src.config import ConfigError, load_settings


def test_defaults_match_the_documented_contract():
    settings = load_settings({})
    assert settings.port == 2026
    assert settings.domain == "www.aihubcampus.online"
    assert settings.db_path == "/app/storage/aihubcampus.db"
    assert settings.retention_days == 30
    assert settings.app_env == "production"
    assert settings.is_production is True
    assert settings.quarantine_dir == "data/quarantine"


def test_environment_overrides_are_applied():
    settings = load_settings(
        {
            "APP_ENV": "staging",
            "APP_DOMAIN": "example.test",
            "APP_PORT": "9001",
            "APP_DB_PATH": "/tmp/test.db",
            "DATA_RETENTION_DAYS": "7",
        }
    )
    assert settings.port == 9001
    assert settings.domain == "example.test"
    assert settings.db_path == "/tmp/test.db"
    assert settings.retention_days == 7
    assert settings.is_production is False


def test_blank_values_fall_back_to_defaults():
    settings = load_settings({"APP_PORT": "  ", "APP_DOMAIN": ""})
    assert settings.port == 2026
    assert settings.domain == "www.aihubcampus.online"


@pytest.mark.parametrize("value", ["not-a-number", "0", "65536", "-1"])
def test_invalid_port_is_rejected(value):
    with pytest.raises(ConfigError):
        load_settings({"APP_PORT": value})


def test_settings_repr_carries_no_secret():
    # The loader must not pull credentials into the settings object at all.
    settings = load_settings(
        {
            "INITIAL_ADMIN_PASSWORD": "super-secret-value",
            "APP_SESSION_SECRET": "another-secret-value",
            "TUNNEL_TOKEN": "token-value",
        }
    )
    rendered = repr(settings)
    assert "super-secret-value" not in rendered
    assert "another-secret-value" not in rendered
    assert "token-value" not in rendered
