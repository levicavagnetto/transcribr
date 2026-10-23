"""`transcribr worker`: run the worker service until it is stopped."""

import logging
import signal
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from types import FrameType

from transcribr.config import Config
from transcribr.ingest.uptime import HEARTBEAT_INTERVAL, Uptime
from transcribr.pipeline.process import JobRunner, ModelPipeline
from transcribr.priority import lower_priority
from transcribr.ravon.client import RavonClient
from transcribr.store.calls import is_listed
from transcribr.store.db import connect
from transcribr.store.migrate import MIGRATIONS_DIR, schema_version
from transcribr.timeutil import utcnow
from transcribr.worker import JobProcessor, Worker

log = logging.getLogger(__name__)

SCHEMA_WAIT_SECONDS = 120


class StoppableClock:
    """Real time, but sleeping wakes early when the worker is asked to stop."""

    def __init__(self, stop: threading.Event) -> None:
        self._stop = stop

    def monotonic(self) -> float:
        return time.monotonic()

    def utcnow(self) -> datetime:
        return utcnow()

    def sleep(self, seconds: float) -> None:
        self._stop.wait(seconds)


def start_heartbeat(
    db_path: Path, stop: threading.Event, *, interval: float = HEARTBEAT_INTERVAL.total_seconds()
) -> threading.Thread:
    """Beat from a thread of its own, so a long transcription doesn't look like a stopped worker."""

    def beat() -> None:
        conn = connect(db_path)
        try:
            while not stop.wait(interval):
                try:
                    Uptime(conn).heartbeat(utcnow())
                except sqlite3.Error as error:
                    log.warning("heartbeat failed: %s", error)
        finally:
            conn.close()

    thread = threading.Thread(target=beat, name="heartbeat", daemon=True)
    thread.start()
    return thread


def run_worker(config: Config, *, process_one: JobProcessor | None = None) -> int:
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        log.info("worker stopping (signal %d)", signum)
        stop.set()

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        return _run(config, stop, process_one)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _run(config: Config, stop: threading.Event, process_one: JobProcessor | None) -> int:
    lower_priority()
    conn = connect(config.database_path)
    expected = len(list(MIGRATIONS_DIR.glob("*.sql")))
    deadline = time.monotonic() + SCHEMA_WAIT_SECONDS
    while schema_version(conn) < expected:
        if stop.is_set() or time.monotonic() > deadline:
            log.error("database schema is not ready (the web service applies migrations)")
            return 1
        log.info("waiting for the web service to prepare the database")
        stop.wait(2)

    password = config.ravon_password.get_secret_value() if config.ravon_password else None
    clock = StoppableClock(stop)

    def make_client(rejected: str | None) -> RavonClient:
        return RavonClient(
            config.ravon_base_url,
            config.ravon_username,
            password,
            is_known_recording=is_listed(conn),
            rejected_fingerprint=rejected,
        )

    worker = Worker.from_state(conn, make_client, clock=clock, stop=stop, process_one=process_one)
    if process_one is None:
        runner = JobRunner(conn, worker.client, ModelPipeline(config.models_dir))
        runner.recover()
        worker.set_processor(runner.process_one)
    heartbeat = start_heartbeat(config.database_path, stop)
    worker.run()
    heartbeat.join()
    log.info("worker stopped")
    return 0
