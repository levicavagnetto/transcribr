"""Deployment configuration from environment variables (the compose `.env` file)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr

from transcribr.redaction import register_secret

DEFAULT_RAVON_BASE_URL = "https://admin.ravon.net"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    ravon_username: str | None
    ravon_password: SecretStr | None
    ravon_base_url: str
    port: int
    data_dir: Path
    models_dir: Path
    ui_dir: Path

    @property
    def has_ravon_credentials(self) -> bool:
        return bool(self.ravon_username) and self.ravon_password is not None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "transcribr.db"


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(f"TRANSCRIBR_PORT must be a number, got {raw!r}") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"TRANSCRIBR_PORT must be between 1 and 65535, got {port}")
    return port


def _base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise ConfigError(f"RAVON_BASE_URL must be an http(s) address, got {raw!r}")
    return url


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Read the configuration; the Ravon password is registered for log redaction."""
    source = os.environ if env is None else env
    username = source.get("RAVON_USERNAME", "").strip() or None
    password_raw = source.get("RAVON_PASSWORD", "")
    password = SecretStr(password_raw) if password_raw else None
    if password_raw:
        register_secret(password_raw)
    return Config(
        ravon_username=username,
        ravon_password=password,
        ravon_base_url=_base_url(source.get("RAVON_BASE_URL", DEFAULT_RAVON_BASE_URL)),
        port=_port(source.get("TRANSCRIBR_PORT", "8000")),
        data_dir=Path(source.get("TRANSCRIBR_DATA_DIR", "/data")),
        models_dir=Path(source.get("TRANSCRIBR_MODELS_DIR", "/models")),
        ui_dir=Path(source.get("TRANSCRIBR_UI_DIR", "/app/ui")),
    )
