import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from transcribr.store.db import connect
from transcribr.store.migrate import migrate


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    migrate(tmp_path / "t.db")
    db = connect(tmp_path / "t.db")
    yield db
    db.close()


def add_call(
    conn: sqlite3.Connection,
    call_id: int,
    lines: Sequence[tuple[float, float]],
    *,
    text: str = "spoken words",
) -> None:
    """A Transcribed call whose lines are (start, end)."""
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', '2026-10-22 08:00:00',"
        " '2026-10-22T13:00:00Z', 2, '(405) 555-0142', 'y', 't', 'transcribed')",
        (call_id,),
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (?, 'en', 'small.en', 't')",
        (call_id,),
    )
    conn.executemany(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text) VALUES (?, ?, ?, ?, ?)",
        [(call_id, idx, start, end, f"{text} {idx}") for idx, (start, end) in enumerate(lines)],
    )
