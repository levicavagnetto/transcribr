"""The worker service's main loop: heartbeats, polling, requests from the web service, and jobs."""

import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from transcribr.ingest.poller import Poller
from transcribr.ingest.uptime import HEARTBEAT_INTERVAL, Uptime
from transcribr.ravon.client import RavonClient, RavonError
from transcribr.ravon.parse import PageFormatChanged
from transcribr.settings import POLL_INTERVAL_MINUTES, Settings
from transcribr.store.state import (
    QUEUE_LIST,
    QUEUE_REFRESH_REQUESTED,
    RAVON_REJECTED_FINGERPRINT,
    RETRY_LOGIN_REQUESTED,
    State,
)
from transcribr.timeutil import from_iso, to_iso

log = logging.getLogger(__name__)

LOAD_EARLIER = "load_earlier"
MAX_IDLE_SLEEP = 1.0
QUEUE_LIST_MAX_AGE = timedelta(hours=6)
QUEUE_LIST_RETRY_SECONDS = 60.0

# Takes the database, does at most one unit of work, and says whether it did any.
JobProcessor = Callable[[sqlite3.Connection], bool]


class WorkerClock(Protocol):
    def monotonic(self) -> float: ...
    def utcnow(self) -> datetime: ...
    def sleep(self, seconds: float) -> None: ...


def request_load_earlier(conn: sqlite3.Connection, now: datetime) -> None:
    """Called by the web service; the worker lists the earlier week on its next loop."""
    conn.execute(
        "INSERT INTO jobs (type, call_id, created_at) VALUES (?, NULL, ?)",
        (LOAD_EARLIER, to_iso(now)),
    )


class Worker:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: RavonClient,
        *,
        clock: WorkerClock,
        stop: threading.Event,
        process_one: JobProcessor | None = None,
    ) -> None:
        self._conn = conn
        self._client = client
        self._clock = clock
        self._stop = stop
        self._process_one = process_one
        self._uptime = Uptime(conn)
        self._poller = Poller(conn, client, self._uptime, now=clock.utcnow)
        self._settings = Settings(conn)
        self._state = State(conn)
        self._started = False
        self._caught_up = False
        self._next_heartbeat = 0.0
        self._last_poll: float | None = None
        self._last_queue_attempt: float | None = None

    @classmethod
    def from_state(
        cls,
        conn: sqlite3.Connection,
        make_client: Callable[[str | None], RavonClient],
        *,
        clock: WorkerClock,
        stop: threading.Event,
        process_one: JobProcessor | None = None,
    ) -> Worker:
        """Build the worker with a client that remembers a rejected login across restarts."""
        rejected: str | None = State(conn).get(RAVON_REJECTED_FINGERPRINT)
        return cls(conn, make_client(rejected), clock=clock, stop=stop, process_one=process_one)

    @property
    def client(self) -> RavonClient:
        return self._client

    def set_processor(self, process_one: JobProcessor) -> None:
        self._process_one = process_one

    def run(self, *, until: float | None = None) -> None:
        """Loop until `stop` is set (or the monotonic clock passes `until`, for tests)."""
        if not self._started:
            self._started = True
            log.info("worker starting")
        while not self._stop.is_set() and (until is None or self._clock.monotonic() < until):
            if not self.step():
                self._clock.sleep(MAX_IDLE_SLEEP)
        self._uptime.heartbeat(self._clock.utcnow())

    def step(self) -> bool:
        """Do whatever is due. Returns True if a job was processed (so don't sleep)."""
        now = self._clock.monotonic()
        if now >= self._next_heartbeat:
            self._uptime.heartbeat(self._clock.utcnow())
            self._next_heartbeat = now + HEARTBEAT_INTERVAL.total_seconds()
        self._handle_retry_login()
        self._handle_load_earlier()
        self._refresh_queue_list(now)
        if self._poll_due(now):
            self._last_poll = now
            result = self._poller.poll() if self._caught_up else self._poller.catch_up()
            self._caught_up = self._caught_up or result.ok
        if self._process_one is None:
            return False
        return self._process_one(self._conn)

    def _poll_due(self, now: float) -> bool:
        if self._last_poll is None:
            return True
        interval = self._settings.get(POLL_INTERVAL_MINUTES) * 60
        return now - self._last_poll >= interval

    def _handle_retry_login(self) -> None:
        if not self._state.get(RETRY_LOGIN_REQUESTED):
            return
        log.info("retrying the Ravon login on request")
        self._client.retry_login()
        self._state.delete(RETRY_LOGIN_REQUESTED)
        self._state.delete(RAVON_REJECTED_FINGERPRINT)
        self._last_poll = None  # poll right away

    def _refresh_queue_list(self, now: float) -> None:
        """Keep the Ravon queue list cached for the admin Settings screen."""
        requested = bool(self._state.get(QUEUE_REFRESH_REQUESTED))
        cached = self._state.get(QUEUE_LIST)
        stale = cached is None or (
            self._clock.utcnow() - from_iso(cached["fetched_at"]) >= QUEUE_LIST_MAX_AGE
        )
        if not (requested or stale):
            return
        recent = self._last_queue_attempt is not None and (
            now - self._last_queue_attempt < QUEUE_LIST_RETRY_SECONDS
        )
        if recent and not requested:
            return
        self._last_queue_attempt = now
        self._state.delete(QUEUE_REFRESH_REQUESTED)
        try:
            queues = self._client.queues()
        except (RavonError, PageFormatChanged) as error:
            log.warning("could not read the Ravon queue list: %s", error)
            return
        self._state.set(
            QUEUE_LIST,
            {
                "fetched_at": to_iso(self._clock.utcnow()),
                "queues": [{"value": q.value, "label": q.label} for q in queues],
            },
        )

    def _handle_load_earlier(self) -> None:
        requested = self._conn.execute(
            "DELETE FROM jobs WHERE type = ? RETURNING id", (LOAD_EARLIER,)
        ).fetchall()
        if requested:
            self._poller.load_earlier()
