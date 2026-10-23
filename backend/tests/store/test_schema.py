import sqlite3
from pathlib import Path

import pytest

from transcribr.store.db import connect, transaction
from transcribr.store.migrate import migrate, schema_version

EXPECTED_TABLES = {
    "calls",
    "jobs",
    "transcripts",
    "segments",
    "segments_fts",
    "speakers",
    "settings",
    "uptime_spans",
    "service_state",
    "admin",
    "admin_sessions",
    "admin_setup_code",
}

EXPECTED_INDEXES = {
    "calls_by_start",
    "calls_by_state",
    "jobs_ready",
    "segments_by_call",
    "admin_sessions_by_expiry",
}


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "transcribr.db"
    migrate(db)
    return connect(db)


def names(conn: sqlite3.Connection, kind: str) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))
    return {r[0] for r in rows}


def test_empty_database_gets_every_table_and_index(conn: sqlite3.Connection) -> None:
    assert schema_version(conn) == 1
    assert names(conn, "table") >= EXPECTED_TABLES
    assert names(conn, "index") >= EXPECTED_INDEXES


def add_call(conn: sqlite3.Connection, call_id: int = 26541125) -> None:
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', '2026-10-22 10:42:00',"
        " '2026-10-22T15:42:00Z', 6.2, '(405) 555-0142', 'SW Counter Sales',"
        " '2026-10-22T15:49:00Z', 'not_transcribed')",
        (call_id,),
    )


def test_call_state_is_restricted(conn: sqlite3.Connection) -> None:
    add_call(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE calls SET state = 'done'")


def test_one_job_per_type_and_call(conn: sqlite3.Connection) -> None:
    add_call(conn)
    conn.execute(
        "INSERT INTO jobs (type, call_id, created_at) VALUES ('transcribe', 26541125, 't')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (type, call_id, created_at) VALUES ('transcribe', 26541125, 't')"
        )


def test_segments_are_searchable_and_follow_edits(conn: sqlite3.Connection) -> None:
    add_call(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
            " VALUES (26541125, 'en', 'small.en', 't')"
        )
        conn.execute(
            "INSERT INTO segments (call_id, idx, start_s, end_s, speaker, text, words)"
            " VALUES (26541125, 0, 48.0, 52.1, 'Speaker 2', 'a three inch lift kit', '[]')"
        )
    hit = conn.execute(
        "SELECT s.call_id, s.start_s FROM segments_fts f JOIN segments s ON s.id = f.rowid"
        " WHERE segments_fts MATCH '\"lift kit\"'"
    ).fetchone()
    assert (hit[0], hit[1]) == (26541125, 48.0)

    conn.execute("DELETE FROM segments")
    count = conn.execute("SELECT count(*) FROM segments_fts WHERE segments_fts MATCH 'lift'")
    assert count.fetchone()[0] == 0


def test_deleting_a_call_removes_its_transcript_and_speakers(conn: sqlite3.Connection) -> None:
    add_call(conn)
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (26541125, 'en', 'small.en', 't')"
    )
    conn.execute(
        "INSERT INTO speakers (call_id, label, speech_seconds, fingerprint)"
        " VALUES (26541125, 'Speaker 1', 12.5, x'00')"
    )
    conn.execute("DELETE FROM calls")
    assert conn.execute("SELECT count(*) FROM transcripts").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM speakers").fetchone()[0] == 0


def test_only_one_admin_row(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO admin (id, username, password_hash, password_changed_at)"
        " VALUES (1, 'admin', 'h', 't')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO admin (id, username, password_hash, password_changed_at)"
            " VALUES (2, 'other', 'h', 't')"
        )
