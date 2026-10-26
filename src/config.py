"""Typed, non-secret environment settings.

Only values that are safe to display and log live here. Credentials
(``INITIAL_ADMIN_PASSWORD``, ``INITIAL_USER_PASSWORD``, ``APP_SESSION_SECRET``,
``TUNNEL_TOKEN``) are read by the code that uses them — never by this module — so a
``Settings`` object can be printed, tested and put in evidence without redaction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

#: Port the app serves on. The Cloudflare ingress targets http://web:2026, so this is
#: not 8501. Single source of truth: docs/architecture.md §5.
DEFAULT_PORT = 2026
DEFAULT_DOMAIN = "www.aihubcampus.online"
DEFAULT_DB_PATH = "/app/storage/aihubcampus.db"
DEFAULT_RETENTION_DAYS = 30


class ConfigError(ValueError):
    """A required setting is present but invalid. The message names the variable only."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    domain: str
    port: int
    db_path: str
    retention_days: int

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _text(environ: Mapping[str, str], name: str, default: str) -> str:
    value = environ.get(name, "").strip()
    return value or default


def _integer(environ: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got a non-numeric value") from None
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build settings from ``environ`` (defaults to ``os.environ``)."""
    env = os.environ if environ is None else environ
    return Settings(
        app_env=_text(env, "APP_ENV", "production").lower(),
        domain=_text(env, "APP_DOMAIN", DEFAULT_DOMAIN),
        port=_integer(env, "APP_PORT", DEFAULT_PORT, 1, 65535),
        db_path=_text(env, "APP_DB_PATH", DEFAULT_DB_PATH),
        retention_days=_integer(env, "DATA_RETENTION_DAYS", DEFAULT_RETENTION_DAYS, 0, 3650),
    )
