import shutil
import sqlite3
from pathlib import Path

import pytest

from transcribr.store.db import connect
from transcribr.store.migrate import MIGRATIONS_DIR, migrate

CALL = 90000001


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A database at version 5 with voice data and every kind of attribution, then upgraded."""
    before = tmp_path / "before"
    before.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("000[1-5]_*.sql")):
        shutil.copy(path, before / path.name)
    db = tmp_path / "transcribr.db"
    migrate(db, migrations_dir=before)
    old = connect(db)
    old.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', '2026-10-22 08:00:00',"
        " '2026-10-22T13:00:00Z', 2, '(405) 555-0142', 'y', 't', 'transcribed')",
        (CALL,),
    )
    old.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (?, 'en', 'small.en', 't')",
        (CALL,),
    )
    old.execute(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text, voiceprint)"
        " VALUES (?, 0, 0.0, 3.0, 'Tire Pros, this is Nolan a lift kit', x'0000803f')",
        (CALL,),
    )
    for pid in (1, 2, 3, 4):
        old.execute(
            "INSERT INTO profiles (id, display_name, created_at) VALUES (?, ?, 't')",
            (pid, f"P{pid}"),
        )
    old.execute("INSERT INTO voice_samples VALUES (1, ?, 0, 't')", (CALL,))
    old.executemany(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, 't')",
        [
            ("voice_threshold_low", "0.6"),
            ("voice_threshold_high", "0.7"),
            ("poll_interval_minutes", "5"),
        ],
    )
    old.executemany(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, name_heard,"
        " name_at_s, voice_score, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 't')",
        [
            (CALL, 1, "confident", "auto", "voice", None, None, 0.8),
            (CALL, 2, "confident", "auto", "name", "Nolan", 2.0, None),
            (CALL, 3, "confident", "manual", "manual", None, None, 0.71),
            (CALL, 4, "rejected", "manual", "manual", None, None, None),
        ],
    )
    old.close()
    assert migrate(db) == [6]
    return connect(db)


def test_voice_data_is_gone(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "voice_samples" not in tables
    assert "voiceprint" not in columns(conn, "segments")
    assert "voice_score" not in columns(conn, "attributions")
    assert [r[0] for r in conn.execute("SELECT key FROM settings")] == ["poll_interval_minutes"]


def test_manual_rows_stay_and_automatic_rows_wait_for_a_rematch(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT profile_id, status, source, method FROM attributions ORDER BY profile_id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (3, "confident", "manual", "manual"),
        (4, "rejected", "manual", "manual"),
    ]
    assert conn.execute("SELECT count(*) FROM jobs WHERE type = 'rematch'").fetchone()[0] == 1


def test_voice_methods_are_refused(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO attributions (call_id, profile_id, status, source, method, updated_at)"
            " VALUES (?, 1, 'maybe', 'auto', 'voice', 't')",
            (CALL,),
        )


def test_transcript_text_and_search_still_work(conn: sqlite3.Connection) -> None:
    assert (
        conn.execute("SELECT text FROM segments WHERE call_id = ?", (CALL,))
        .fetchone()[0]
        .endswith("lift kit")
    )
    found = conn.execute(
        "SELECT rowid FROM segments_fts WHERE segments_fts MATCH 'lift'"
    ).fetchall()
    assert len(found) == 1
