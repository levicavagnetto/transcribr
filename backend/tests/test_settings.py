import sqlite3
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from transcribr.settings import (
    POLL_INTERVAL_MINUTES,
    STORE_QUEUES,
    TIME_ZONE,
    Setting,
    SettingError,
    Settings,
    register,
)
from transcribr.store.db import connect
from transcribr.store.migrate import migrate


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "transcribr.db"
    migrate(db)
    return connect(db)


def test_defaults_on_a_new_instance(conn: sqlite3.Connection) -> None:
    settings = Settings(conn)
    assert settings.get(STORE_QUEUES) == []
    assert settings.get(POLL_INTERVAL_MINUTES) == 2
    assert settings.get(TIME_ZONE) == "America/Chicago"


def test_a_change_is_seen_by_another_connection_without_restart(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    worker = Settings(connect(tmp_path / "transcribr.db"))
    assert worker.get(POLL_INTERVAL_MINUTES) == 2
    Settings(conn).set(POLL_INTERVAL_MINUTES, 5)
    assert worker.get(POLL_INTERVAL_MINUTES) == 5


@pytest.mark.parametrize("value", [0, 31, -1, "two"])
def test_poll_interval_out_of_range_is_rejected(conn: sqlite3.Connection, value: object) -> None:
    settings = Settings(conn)
    with pytest.raises(SettingError, match="1 and 30") as info:
        settings.set(POLL_INTERVAL_MINUTES, value)
    assert info.value.key == "poll_interval_minutes"
    assert settings.get(POLL_INTERVAL_MINUTES) == 2


def test_unknown_time_zone_is_rejected(conn: sqlite3.Connection) -> None:
    settings = Settings(conn)
    with pytest.raises(SettingError, match="time zone"):
        settings.set(TIME_ZONE, "America/Atlantis")
    settings.set(TIME_ZONE, "America/Denver")
    assert settings.get(TIME_ZONE) == "America/Denver"


def test_queues_are_cleaned_and_deduplicated(conn: sqlite3.Connection) -> None:
    settings = Settings(conn)
    settings.set(
        STORE_QUEUES, [" tireProz-salescustserv ", "tireProz-SWafterHRS", "tireProz-SWafterHRS"]
    )
    assert settings.get(STORE_QUEUES) == ["tireProz-salescustserv", "tireProz-SWafterHRS"]
    with pytest.raises(SettingError):
        settings.set(STORE_QUEUES, ["", "  "])


def test_unknown_key_is_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(SettingError, match="unknown setting"):
        Settings(conn).set_by_key("favourite_colour", "orange")


def test_a_corrupt_stored_value_falls_back_to_the_default(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO settings (key, value, updated_at)"
        " VALUES ('poll_interval_minutes', '\"x\"', 't')"
    )
    assert Settings(conn).get(POLL_INTERVAL_MINUTES) == 2


def test_later_changes_can_register_settings(conn: sqlite3.Connection) -> None:
    greeting = register(
        Setting(key="test_greeting", adapter=TypeAdapter(str), default="hi", label="Greeting")
    )
    settings = Settings(conn)
    assert settings.get(greeting) == "hi"
    settings.set(greeting, "hello")
    assert settings.as_dict()["test_greeting"] == "hello"
    with pytest.raises(ValueError, match="already registered"):
        register(Setting(key="test_greeting", adapter=TypeAdapter(str), default="x", label="x"))
