"""SQLite connections shared by the web and worker services."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def digits_only(text: str | None) -> str:
    """A phone number's digits, so "(405) 555-0142" and "405.555.0142" compare equal."""
    return "".join(ch for ch in text or "" if ch in "0123456789")


def connect(path: Path) -> sqlite3.Connection:
    """Open the database in WAL mode with foreign keys on.

    The connection is in autocommit mode; group writes with `transaction()`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("digits_only", 1, digits_only, deterministic=True)
    return conn


def copy_database(conn: sqlite3.Connection, target: Path) -> None:
    """Write a consistent copy of the open database to `target` (the SQLite backup API)."""
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)
    finally:
        copy.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """Run a block as one write transaction, taking the write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
