"""Instance settings: a registry of typed settings stored as JSON in the `settings` table.

Reads always go to the database, so a change made by one service is seen by the other
without a restart. Later changes add their own settings with `register()`.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

log = logging.getLogger(__name__)


class SettingError(ValueError):
    """A rejected setting value, with a message meant for the admin."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key
        self.message = message


@dataclass(frozen=True)
class Setting[T]:
    key: str
    adapter: TypeAdapter[T]
    default: T
    label: str
    message: str = "Invalid value."


_REGISTRY: dict[str, Setting[Any]] = {}


def register[T](setting: Setting[T]) -> Setting[T]:
    if setting.key in _REGISTRY:
        raise ValueError(f"setting {setting.key!r} is already registered")
    _REGISTRY[setting.key] = setting
    return setting


def registered() -> dict[str, Setting[Any]]:
    return dict(_REGISTRY)


def _clean_queues(queues: list[str]) -> list[str]:
    cleaned: list[str] = []
    for queue in queues:
        name = queue.strip()
        if not name:
            raise ValueError("empty queue name")
        if name not in cleaned:
            cleaned.append(name)
    return cleaned


def _known_time_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"unknown time zone {name!r}") from error
    return name


STORE_QUEUES = register(
    Setting(
        key="store_queues",
        adapter=TypeAdapter(Annotated[list[str], AfterValidator(_clean_queues)]),
        default=[],
        label="Store queues",
        message="Each store queue must be a non-empty Ravon queue name.",
    )
)

POLL_INTERVAL_MINUTES = register(
    Setting(
        key="poll_interval_minutes",
        adapter=TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=30)]),
        default=2,
        label="Check for new calls every (minutes)",
        message="The poll interval must be a whole number of minutes between 1 and 30.",
    )
)

TIME_ZONE = register(
    Setting(
        key="time_zone",
        adapter=TypeAdapter(Annotated[str, AfterValidator(_known_time_zone)]),
        default="America/Chicago",
        label="Store time zone",
        message="Unknown time zone. Use a name like America/Chicago.",
    )
)


class Settings:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get[T](self, setting: Setting[T]) -> T:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (setting.key,)
        ).fetchone()
        if row is None:
            return setting.default
        try:
            return setting.adapter.validate_json(row["value"])
        except ValidationError:
            log.warning("stored value for setting %s is invalid; using the default", setting.key)
            return setting.default

    def set[T](self, setting: Setting[T], value: object) -> T:
        try:
            clean = setting.adapter.validate_python(value)
        except ValidationError as error:
            raise SettingError(setting.key, setting.message) from error
        now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        self._conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE"
            " SET value = excluded.value, updated_at = excluded.updated_at",
            (setting.key, setting.adapter.dump_json(clean).decode(), now),
        )
        return clean

    def set_by_key(self, key: str, value: object) -> object:
        setting = _REGISTRY.get(key)
        if setting is None:
            raise SettingError(key, f"unknown setting {key!r}")
        return self.set(setting, value)

    def as_dict(self) -> dict[str, Any]:
        return {key: self.get(setting) for key, setting in _REGISTRY.items()}
