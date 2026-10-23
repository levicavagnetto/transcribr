import sqlite3
import threading
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from tests.clock import FakeClock
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.ravon.client import RavonClient, credential_fingerprint
from transcribr.settings import POLL_INTERVAL_MINUTES, STORE_QUEUES, Settings
from transcribr.store.db import connect
from transcribr.store.migrate import migrate
from transcribr.store.state import (
    RAVON_REJECTED_FINGERPRINT,
    RAVON_STATE,
    RETRY_LOGIN_REQUESTED,
    State,
)
from transcribr.timeutil import utc_to_local
from transcribr.worker import Worker, request_load_earlier

QUEUE = "tireProz-salescustserv"


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        migrate(tmp_path / "t.db")
        self.conn = connect(tmp_path / "t.db")
        Settings(self.conn).set(STORE_QUEUES, [QUEUE])
        self.clock = FakeClock()
        self.fake = FakeRavon(now=self.clock.utcnow)
        self.processed: list[int] = []
        self.stop = threading.Event()
        self.worker = self.make_worker()

    def make_worker(self, rejected: str | None = None) -> Worker:
        client = RavonClient(
            "https://admin.ravon.net",
            self.fake.username,
            self.fake.password,
            transport=httpx.MockTransport(self.fake.handle),
            clock=self.clock,
            rejected_fingerprint=rejected,
        )
        return Worker(
            self.conn, client, clock=self.clock, process_one=self.process_one, stop=self.stop
        )

    def process_one(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute("SELECT call_id FROM jobs WHERE type = 'transcribe' LIMIT 1").fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM jobs WHERE call_id = ?", (row[0],))
        conn.execute("UPDATE calls SET state = 'transcribed' WHERE id = ?", (row[0],))
        self.processed.append(row[0])
        return True

    def add_call(self, rid: int, ends_in_minutes: float, length: float = 3.0) -> None:
        end = self.clock.utcnow() + timedelta(minutes=ends_in_minutes)
        start = utc_to_local(end - timedelta(minutes=length), "America/Chicago")
        self.fake.calls.append(FakeCall(rid, QUEUE, start.strftime("%Y-%m-%d %H:%M:%S"), length))

    def run_minutes(self, minutes: float) -> None:
        self.worker.run(until=self.clock.now + minutes * 60)

    def searches(self) -> int:
        return sum(1 for r in self.fake.requests if r.method == "POST" and "recorded" in r.url.path)

    def spans(self) -> int:
        return self.conn.execute("SELECT count(*) FROM uptime_spans").fetchone()[0]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_a_simulated_hour(rig: Rig) -> None:
    rig.add_call(11111111, ends_in_minutes=-60 * 24)  # yesterday: listed by catch-up only
    rig.run_minutes(1)
    assert rig.conn.execute("SELECT state FROM calls").fetchone()[0] == "not_transcribed"

    rig.add_call(22222222, ends_in_minutes=10)
    rig.add_call(33333333, ends_in_minutes=25, length=8)
    rig.run_minutes(59)

    # One catch-up search, then a poll every 2 minutes for the rest of the hour.
    assert 29 <= rig.searches() <= 32
    assert rig.spans() == 1
    assert rig.processed == [22222222, 33333333]
    states = dict(rig.conn.execute("SELECT id, state FROM calls").fetchall())
    assert states == {
        11111111: "not_transcribed",
        22222222: "transcribed",
        33333333: "transcribed",
    }


def test_the_poll_interval_setting_applies_without_restart(rig: Rig) -> None:
    rig.run_minutes(10)
    before = rig.searches()
    Settings(rig.conn).set(POLL_INTERVAL_MINUTES, 5)
    rig.run_minutes(30)
    assert 5 <= rig.searches() - before <= 7


def test_load_earlier_requests_are_carried_out(rig: Rig) -> None:
    rig.add_call(44444444, ends_in_minutes=-60 * 24 * 10)  # 10 days ago
    rig.run_minutes(1)
    assert rig.conn.execute("SELECT count(*) FROM calls").fetchone()[0] == 0
    request_load_earlier(rig.conn, rig.clock.utcnow())
    rig.run_minutes(1)
    assert rig.conn.execute("SELECT id FROM calls").fetchone()[0] == 44444444
    assert rig.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_a_retry_login_request_is_honoured(rig: Rig) -> None:
    rig.fake.reject_logins = True
    rig.run_minutes(5)
    state = State(rig.conn)
    assert state.get(RAVON_STATE) == "login_failed"
    assert state.get(RAVON_REJECTED_FINGERPRINT) is not None

    rig.fake.reject_logins = False
    state.set(RETRY_LOGIN_REQUESTED, True)
    rig.run_minutes(3)
    assert state.get(RAVON_STATE) == "ok"
    assert state.get(RETRY_LOGIN_REQUESTED) is None


def test_a_rejected_login_is_remembered_across_restarts(rig: Rig) -> None:
    fingerprint = credential_fingerprint(rig.fake.username, rig.fake.password)
    State(rig.conn).set(RAVON_REJECTED_FINGERPRINT, fingerprint)
    worker = Worker.from_state(
        rig.conn,
        lambda rejected: RavonClient(
            "https://admin.ravon.net",
            rig.fake.username,
            rig.fake.password,
            transport=httpx.MockTransport(rig.fake.handle),
            clock=rig.clock,
            rejected_fingerprint=rejected,
        ),
        clock=rig.clock,
        stop=rig.stop,
    )
    worker.run(until=rig.clock.now + 300)
    assert rig.fake.requests == []  # no login attempt with the same credentials


def test_stop_ends_the_loop_after_the_current_step(rig: Rig) -> None:
    rig.run_minutes(1)
    rig.stop.set()
    start = rig.clock.now
    rig.worker.run(until=rig.clock.now + 3600)
    assert rig.clock.now - start < 5


def test_worker_command_refuses_an_unprepared_database(tmp_path: Path) -> None:
    from transcribr import run_worker as module
    from transcribr.config import load_config

    original = module.SCHEMA_WAIT_SECONDS
    module.SCHEMA_WAIT_SECONDS = 0
    try:
        code = module.run_worker(load_config({"TRANSCRIBR_DATA_DIR": str(tmp_path)}))
    finally:
        module.SCHEMA_WAIT_SECONDS = original
    assert code == 1


def test_the_queue_list_is_cached_at_start_even_before_queues_are_chosen(rig: Rig) -> None:
    from transcribr.store.state import QUEUE_LIST

    Settings(rig.conn).set(STORE_QUEUES, [])
    rig.run_minutes(1)
    cached = State(rig.conn).get(QUEUE_LIST)
    assert [q["value"] for q in cached["queues"]] == list(rig.fake.queues)
    assert cached["queues"][0]["label"] == "Stillwater Sales/CS (x600)"


def test_the_queue_list_refreshes_on_request_and_when_stale(rig: Rig) -> None:
    from transcribr.store.state import QUEUE_LIST, QUEUE_REFRESH_REQUESTED

    def page_loads() -> int:
        return sum(1 for r in rig.fake.requests if r.method == "GET" and "recorded" in r.url.path)

    rig.run_minutes(1)
    assert page_loads() == 1
    rig.run_minutes(30)
    assert page_loads() == 1  # cached

    State(rig.conn).set(QUEUE_REFRESH_REQUESTED, True)
    rig.run_minutes(1)
    assert page_loads() == 2
    assert State(rig.conn).get(QUEUE_REFRESH_REQUESTED) is None

    rig.fake.queues["tireProz-new"] = "New Queue (x900)"
    rig.run_minutes(6 * 60)
    assert page_loads() == 3
    assert "tireProz-new" in [q["value"] for q in State(rig.conn).get(QUEUE_LIST)["queues"]]


def test_a_changed_page_does_not_stop_the_worker(rig: Rig) -> None:
    rig.fake.page_format_changed = True
    rig.fake.queue_select_missing = True
    rig.run_minutes(5)  # would raise if an exception escaped the loop
    assert State(rig.conn).get(RAVON_STATE) == "page_format_changed"
