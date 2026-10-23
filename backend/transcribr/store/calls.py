"""Listing calls and queuing their transcription jobs."""

import sqlite3
from datetime import datetime, timedelta

from transcribr.ravon.parse import Recording
from transcribr.store.db import transaction
from transcribr.timeutil import local_to_utc, to_iso

START_FORMAT = "%Y-%m-%d %H:%M:%S"
TRANSCRIBE = "transcribe"


def call_times(recording: Recording, zone: str) -> tuple[datetime, datetime]:
    """The call's start and end in UTC."""
    start = local_to_utc(datetime.strptime(recording.start_local, START_FORMAT), zone)
    return start, start + timedelta(minutes=recording.minutes)


def add_listed(  # noqa: PLR0913 - keyword-only call details
    conn: sqlite3.Connection,
    recording: Recording,
    *,
    queue: str,
    zone: str,
    now: datetime,
    auto_queue: bool,
) -> bool:
    """Insert a newly seen call (and its job if auto_queue). False if it was already listed."""
    start_utc, _ = call_times(recording, zone)
    with transaction(conn):
        inserted = conn.execute(
            "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
            " answered_by, listed_at, state, auto_queued) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (id) DO NOTHING",
            (
                recording.id,
                queue,
                recording.start_local,
                to_iso(start_utc),
                recording.minutes,
                recording.caller,
                recording.answered_by,
                to_iso(now),
                "waiting" if auto_queue else "not_transcribed",
                int(auto_queue),
            ),
        ).rowcount
        if inserted and auto_queue:
            enqueue_transcribe(conn, recording.id, now)
    return bool(inserted)


def enqueue_transcribe(conn: sqlite3.Connection, call_id: int, now: datetime) -> None:
    conn.execute(
        "INSERT INTO jobs (type, call_id, created_at) VALUES (?, ?, ?)"
        " ON CONFLICT (type, call_id) DO NOTHING",
        (TRANSCRIBE, call_id, to_iso(now)),
    )


def oldest_start_utc(conn: sqlite3.Connection) -> str | None:
    value: str | None = conn.execute("SELECT min(start_utc) FROM calls").fetchone()[0]
    return value


def newest_start_utc(conn: sqlite3.Connection) -> str | None:
    value: str | None = conn.execute("SELECT max(start_utc) FROM calls").fetchone()[0]
    return value
