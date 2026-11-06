"""Queuing a rematch job (design D6). Kept apart so profiles and samples can queue one."""

import sqlite3
from datetime import datetime

from transcribr.timeutil import to_iso

REMATCH = "rematch"


def request_rematch(conn: sqlite3.Connection, now: datetime) -> None:
    """Queue a rematch of every transcribed call, unless one is already waiting to start.

    A rematch that is already running read the old profiles, so it doesn't count.
    """
    pending = conn.execute(
        "SELECT 1 FROM jobs WHERE type = ? AND claimed_at IS NULL", (REMATCH,)
    ).fetchone()
    if pending is None:
        conn.execute(
            "INSERT INTO jobs (type, call_id, created_at) VALUES (?, NULL, ?)",
            (REMATCH, to_iso(now)),
        )
