"""Operator commands: the worker's Docker health check and database backups (design D11)."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from transcribr.store.db import copy_database
from transcribr.timeutil import from_iso

WORKER_HEALTHY_WITHIN = timedelta(seconds=90)


def heartbeat_age(conn: sqlite3.Connection, now: datetime) -> timedelta | None:
    """How long ago the worker last beat, or None if it never has."""
    last_seen: str | None = conn.execute("SELECT max(last_seen_at) FROM uptime_spans").fetchone()[0]
    return None if last_seen is None else now - from_iso(last_seen)


def backup_database(conn: sqlite3.Connection, backups_dir: Path, now: datetime) -> Path:
    """Copy the database to `backups_dir/transcribr-<timestamp>.db` and return the path."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    target = backups_dir / f"transcribr-{stamp}.db"
    number = 1
    while target.exists():
        number += 1
        target = backups_dir / f"transcribr-{stamp}-{number}.db"
    copy_database(conn, target)
    return target
