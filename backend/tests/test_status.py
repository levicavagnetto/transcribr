import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from tests.clock import EPOCH
from transcribr.ingest.uptime import Uptime
from transcribr.settings import POLL_INTERVAL_MINUTES, STORE_QUEUES, Settings
from transcribr.status import Status, build_status
from transcribr.store.db import connect
from transcribr.store.migrate import migrate
from transcribr.store.state import GUARD_VIOLATIONS, LAST_POLL_OK, RAVON_ERROR, RAVON_STATE, State
from transcribr.timeutil import from_iso, to_iso

NOW = EPOCH


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    migrate(tmp_path / "t.db")
    conn = connect(tmp_path / "t.db")
    Settings(conn).set(STORE_QUEUES, ["tireProz-salescustserv"])
    yield conn
    conn.close()


def working(conn: sqlite3.Connection) -> None:
    """A worker that beat 30 seconds ago and polled Ravon a minute ago."""
    Uptime(conn).heartbeat(NOW - timedelta(minutes=10))
    Uptime(conn).heartbeat(NOW - timedelta(seconds=30))
    State(conn).set(LAST_POLL_OK, to_iso(NOW - timedelta(minutes=1)))
    State(conn).set(RAVON_STATE, "ok")


def status(conn: sqlite3.Connection, *, credentials: bool = True) -> Status:
    return build_status(conn, now=NOW, credentials_present=credentials, admin_exists=True)


def test_healthy(conn: sqlite3.Connection) -> None:
    working(conn)
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (1, 'q', '2026-10-22 08:55:00',"
        " '2026-10-22T13:55:00Z', 2, 'x', 'y', 't', 'waiting')"
    )
    report = status(conn)
    assert report.worker_running is True
    assert report.ravon_state == "ok"
    assert report.ravon_error is None
    assert report.last_poll_ok is not None
    interval = timedelta(minutes=Settings(conn).get(POLL_INTERVAL_MINUTES))
    assert NOW - from_iso(report.last_poll_ok) <= interval
    assert report.waiting == 1
    assert report.failed_last_24h == 0
    assert report.guard_violations == 0


@pytest.mark.parametrize(
    ("silent_for", "running"),
    [(timedelta(minutes=2, seconds=59), True), (timedelta(minutes=3), False)],
)
def test_worker_stopped_after_three_silent_minutes(
    conn: sqlite3.Connection, silent_for: timedelta, running: bool
) -> None:
    Uptime(conn).heartbeat(NOW - silent_for)
    assert status(conn).worker_running is running


def test_worker_never_started(conn: sqlite3.Connection) -> None:
    report = status(conn)
    assert report.worker_running is False
    assert report.worker_last_seen is None
    assert report.ravon_state == "unknown"


def test_login_failed(conn: sqlite3.Connection) -> None:
    working(conn)
    State(conn).set(RAVON_STATE, "login_failed")
    State(conn).set(RAVON_ERROR, "Ravon rejected the username or password")
    report = status(conn)
    assert report.worker_running is True
    assert report.ravon_state == "login_failed"
    assert report.ravon_error == "Ravon rejected the username or password"


def test_no_credentials_wins_over_the_stored_state(conn: sqlite3.Connection) -> None:
    working(conn)
    report = status(conn, credentials=False)
    assert report.ravon_state == "no_credentials"
    assert report.ravon_error is None


def test_unreachable(conn: sqlite3.Connection) -> None:
    working(conn)
    State(conn).set(LAST_POLL_OK, to_iso(NOW - timedelta(minutes=25)))
    State(conn).set(RAVON_STATE, "unreachable")
    State(conn).set(RAVON_ERROR, "ConnectError: connection refused")
    report = status(conn)
    assert report.ravon_state == "unreachable"
    assert report.ravon_error == "ConnectError: connection refused"
    assert report.last_poll_ok == to_iso(NOW - timedelta(minutes=25))


def test_allow_list_violations_are_counted(conn: sqlite3.Connection) -> None:
    working(conn)
    State(conn).set(GUARD_VIOLATIONS, 2)
    assert status(conn).guard_violations == 2
