import sqlite3

import pytest

from transcribr.settings import VOICE_HIGH, VOICE_LOW, SettingError, Settings


def test_provisional_defaults(conn: sqlite3.Connection) -> None:
    settings = Settings(conn)
    assert (settings.get(VOICE_LOW), settings.get(VOICE_HIGH)) == (0.50, 0.65)


@pytest.mark.parametrize("value", [-0.1, 1.01, "0.5", True, None, float("nan")])
def test_a_threshold_must_be_a_number_from_0_to_1(conn: sqlite3.Connection, value: object) -> None:
    with pytest.raises(SettingError) as refused:
        Settings(conn).set(VOICE_HIGH, value)
    assert refused.value.message == "Each voice threshold must be a number from 0 to 1."
    assert Settings(conn).get(VOICE_HIGH) == 0.65


@pytest.mark.parametrize(("low", "high"), [(0.7, 0.6), (0.6, 0.6)])
def test_low_must_be_below_high(conn: sqlite3.Connection, low: float, high: float) -> None:
    settings = Settings(conn)
    with pytest.raises(SettingError) as refused:
        settings.set_many({VOICE_LOW.key: low, VOICE_HIGH.key: high})
    assert refused.value.key == VOICE_LOW.key
    assert (settings.get(VOICE_LOW), settings.get(VOICE_HIGH)) == (0.50, 0.65)


def test_the_rule_checks_against_the_saved_value(conn: sqlite3.Connection) -> None:
    settings = Settings(conn)
    with pytest.raises(SettingError):
        settings.set(VOICE_LOW, 0.8)  # above the saved high of 0.65
    settings.set_many({VOICE_LOW.key: 0.8, VOICE_HIGH.key: 0.9})  # both at once is fine
    assert (settings.get(VOICE_LOW), settings.get(VOICE_HIGH)) == (0.8, 0.9)
    settings.set(VOICE_HIGH, 1)
    assert settings.get(VOICE_HIGH) == 1.0
