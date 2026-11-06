"""When the worker was running, from heartbeats stored as spans (design D4)."""

import sqlite3
from datetime import datetime, timedelta

from transcribr.timeutil import from_iso, to_iso

HEARTBEAT_INTERVAL = timedelta(seconds=30)
SPAN_GAP = timedelta(minutes=3)
GRACE = timedelta(minutes=2)


class Uptime:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def heartbeat(self, now: datetime) -> None:
        """Extend the latest span if it was seen within SPAN_GAP, otherwise start a new one."""
        latest = self._conn.execute(
            "SELECT id, last_seen_at FROM uptime_spans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest is not None and now - from_iso(latest["last_seen_at"]) <= SPAN_GAP:
            self._conn.execute(
                "UPDATE uptime_spans SET last_seen_at = max(last_seen_at, ?) WHERE id = ?",
                (to_iso(now), latest["id"]),
            )
            return
        self._conn.execute(
            "INSERT INTO uptime_spans (started_at, last_seen_at) VALUES (?, ?)",
            (to_iso(now), to_iso(now)),
        )

    def was_running(self, moment: datetime) -> bool:
        """Whether `moment` falls inside a span, with GRACE on each side."""
        row = self._conn.execute(
            "SELECT 1 FROM uptime_spans WHERE started_at <= ? AND last_seen_at >= ? LIMIT 1",
            (to_iso(moment + GRACE), to_iso(moment - GRACE)),
        ).fetchone()
        return row is not None
