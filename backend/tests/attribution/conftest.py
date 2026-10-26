import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from transcribr.store.db import connect
from transcribr.store.migrate import migrate

DIM = 8  # real voiceprints have 256 values; the maths doesn't care


def voice(*weights: float) -> np.ndarray:
    """A unit-length test voiceprint pointing mostly along the given axes."""
    vector = np.zeros(DIM, dtype=np.float32)
    vector[: len(weights)] = weights
    return (vector / np.linalg.norm(vector)).astype(np.float32)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    migrate(tmp_path / "t.db")
    db = connect(tmp_path / "t.db")
    yield db
    db.close()


def add_call(
    conn: sqlite3.Connection,
    call_id: int,
    lines: Sequence[tuple[float, float, np.ndarray | None]],
    *,
    text: str = "spoken words",
) -> None:
    """A Transcribed call whose lines are (start, end, voiceprint or None)."""
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
        "INSERT INTO segments (call_id, idx, start_s, end_s, text, voiceprint)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (call_id, idx, start, end, f"{text} {idx}", None if vp is None else vp.tobytes())
            for idx, (start, end, vp) in enumerate(lines)
        ],
    )
