import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from transcribr.ingest.uptime import Uptime
from transcribr.store.db import connect
from transcribr.store.migrate import migrate

T0 = datetime(2026, 10, 22, 14, 0, 0, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    migrate(tmp_path / "t.db")
    return connect(tmp_path / "t.db")


def spans(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return [tuple(r) for r in conn.execute("SELECT started_at, last_seen_at FROM uptime_spans")]


def test_heartbeats_within_three_minutes_extend_one_span(conn: sqlite3.Connection) -> None:
    uptime = Uptime(conn)
    for minutes in (0, 0.5, 1, 3.5, 6):
        uptime.heartbeat(T0 + timedelta(minutes=minutes))
    assert spans(conn) == [("2026-10-22T14:00:00Z", "2026-10-22T14:06:00Z")]


def test_a_gap_over_three_minutes_starts_a_new_span(conn: sqlite3.Connection) -> None:
    uptime = Uptime(conn)
    uptime.heartbeat(T0)
    uptime.heartbeat(T0 + timedelta(minutes=1))
    uptime.heartbeat(T0 + timedelta(minutes=4, seconds=1))  # 3 min 1 s after the last one
    assert len(spans(conn)) == 2


def test_running_includes_the_span_and_two_minutes_either_side(conn: sqlite3.Connection) -> None:
    uptime = Uptime(conn)
    uptime.heartbeat(T0)
    uptime.heartbeat(T0 + timedelta(minutes=2))
    assert uptime.was_running(T0 + timedelta(minutes=1))
    assert uptime.was_running(T0 - timedelta(minutes=2))  # grace before
    assert uptime.was_running(T0 + timedelta(minutes=4))  # grace after
    assert not uptime.was_running(T0 - timedelta(minutes=2, seconds=1))
    assert not uptime.was_running(T0 + timedelta(minutes=4, seconds=1))


def test_downtime_between_spans_is_not_running(conn: sqlite3.Connection) -> None:
    uptime = Uptime(conn)
    uptime.heartbeat(T0)
    uptime.heartbeat(T0 + timedelta(hours=2))  # the server was off in between
    assert not uptime.was_running(T0 + timedelta(hours=1))
    assert uptime.was_running(T0 + timedelta(hours=2))


def test_nothing_runs_before_the_first_heartbeat(conn: sqlite3.Connection) -> None:
    assert not Uptime(conn).was_running(T0)


def test_heartbeat_going_backwards_does_not_shrink_a_span(conn: sqlite3.Connection) -> None:
    uptime = Uptime(conn)
    uptime.heartbeat(T0 + timedelta(minutes=2))
    uptime.heartbeat(T0 + timedelta(minutes=1))  # a clock step back
    assert spans(conn) == [("2026-10-22T14:02:00Z", "2026-10-22T14:02:00Z")]
