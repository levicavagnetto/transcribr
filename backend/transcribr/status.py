"""The instance's health report, read by the status API, the banner and the home page."""

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from transcribr.settings import STORE_QUEUES, TIME_ZONE, Settings
from transcribr.store.state import GUARD_VIOLATIONS, LAST_POLL_OK, RAVON_ERROR, RAVON_STATE, State
from transcribr.timeutil import from_iso, to_iso, utc_to_local

WORKER_STOPPED_AFTER = timedelta(minutes=3)


@dataclass(frozen=True)
class Status:
    worker_running: bool
    worker_last_seen: str | None
    last_poll_ok: str | None
    ravon_state: (
        str  # ok | login_failed | unreachable | no_credentials | page_format_changed | unknown
    )
    ravon_error: str | None
    queues_chosen: bool
    admin_exists: bool
    listed_today: int
    transcribed_today: int
    waiting: int
    failed_last_24h: int
    guard_violations: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_status(
    conn: sqlite3.Connection, *, now: datetime, credentials_present: bool, admin_exists: bool
) -> Status:
    state = State(conn)
    settings = Settings(conn)
    last_seen_row = conn.execute("SELECT max(last_seen_at) FROM uptime_spans").fetchone()
    last_seen: str | None = last_seen_row[0]
    running = last_seen is not None and now - from_iso(last_seen) < WORKER_STOPPED_AFTER

    today = utc_to_local(now, settings.get(TIME_ZONE)).date().isoformat()
    listed, transcribed = conn.execute(
        "SELECT count(*), coalesce(sum(state = 'transcribed'), 0) FROM calls"
        " WHERE start_local LIKE ? || '%'",
        (today,),
    ).fetchone()
    waiting = conn.execute(
        "SELECT count(*) FROM calls WHERE state IN ('waiting', 'processing')"
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT count(*) FROM calls WHERE state = 'failed' AND failed_at >= ?",
        (to_iso(now - timedelta(hours=24)),),
    ).fetchone()[0]

    ravon_state = state.get(RAVON_STATE) or "unknown"
    if not credentials_present:
        ravon_state = "no_credentials"
    return Status(
        worker_running=running,
        worker_last_seen=last_seen,
        last_poll_ok=state.get(LAST_POLL_OK),
        ravon_state=ravon_state,
        ravon_error=state.get(RAVON_ERROR) if ravon_state != "ok" else None,
        queues_chosen=bool(settings.get(STORE_QUEUES)),
        admin_exists=admin_exists,
        listed_today=int(listed),
        transcribed_today=int(transcribed),
        waiting=int(waiting),
        failed_last_24h=int(failed),
        guard_violations=int(state.get(GUARD_VIOLATIONS, 0)),
    )
