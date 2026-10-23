import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl

import httpx

from tests.clock import FakeClock
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.ingest.poller import Poller
from transcribr.ingest.uptime import HEARTBEAT_INTERVAL, Uptime
from transcribr.ravon.client import RavonClient
from transcribr.settings import STORE_QUEUES, Settings
from transcribr.store.db import connect
from transcribr.store.migrate import migrate
from transcribr.timeutil import utc_to_local

STILLWATER = "tireProz-salescustserv"
AFTER_HOURS = "tireProz-SWafterHRS"
ZONE = "America/Chicago"


@dataclass
class Rig:
    conn: sqlite3.Connection
    clock: FakeClock
    fake: FakeRavon
    client: RavonClient
    uptime: Uptime
    poller: Poller

    def run_for(self, minutes: float, *, poll_every: float | None = None) -> None:
        """Advance time with a heartbeat every 30 s, optionally polling on a schedule."""
        end = self.clock.now + minutes * 60
        next_poll = self.clock.now
        while self.clock.now < end:
            self.uptime.heartbeat(self.clock.utcnow())
            if poll_every is not None and self.clock.now >= next_poll:
                self.poller.poll()
                next_poll = self.clock.now + poll_every * 60
            self.clock.advance(HEARTBEAT_INTERVAL.total_seconds())
        self.uptime.heartbeat(self.clock.utcnow())

    def off_for(self, minutes: float) -> None:
        self.clock.advance(minutes * 60)

    def call_ending(
        self, minutes_ago: float, length: float = 3.0, *, rid: int, queue: str = STILLWATER
    ) -> FakeCall:
        """Add a call to the fake that ended `minutes_ago` before now."""
        end = self.clock.utcnow() - timedelta(minutes=minutes_ago)
        start = utc_to_local(end - timedelta(minutes=length), ZONE)
        call = FakeCall(rid, queue, start.strftime("%Y-%m-%d %H:%M:%S"), length)
        self.fake.calls.append(call)
        return call

    def state_of(self, rid: int) -> str | None:
        row = self.conn.execute("SELECT state FROM calls WHERE id = ?", (rid,)).fetchone()
        return None if row is None else row["state"]

    def jobs(self) -> list[int]:
        return [r[0] for r in self.conn.execute("SELECT call_id FROM jobs ORDER BY call_id")]

    def search_windows(self) -> list[tuple[str, str, str]]:
        windows: list[tuple[str, str, str]] = []
        for request in self.fake.requests:
            if request.method == "POST" and request.url.path.endswith("manage_recorded_calls.html"):
                form = dict(parse_qsl(request.content.decode(), keep_blank_values=True))
                windows.append((form["queue"], form["startDate"], form["endDate"]))
        return windows


def make_rig(tmp_path: Path, queues: list[str] | None = None, *, credentials: bool = True) -> Rig:
    db = tmp_path / "transcribr.db"
    migrate(db)
    conn = connect(db)
    Settings(conn).set(STORE_QUEUES, [STILLWATER] if queues is None else queues)
    clock = FakeClock()
    fake = FakeRavon(now=clock.utcnow)
    client = RavonClient(
        "https://admin.ravon.net",
        fake.username if credentials else None,
        fake.password if credentials else None,
        transport=httpx.MockTransport(fake.handle),
        clock=clock,
    )
    uptime = Uptime(conn)
    poller = Poller(conn, client, uptime, now=clock.utcnow)
    return Rig(conn, clock, fake, client, uptime, poller)
