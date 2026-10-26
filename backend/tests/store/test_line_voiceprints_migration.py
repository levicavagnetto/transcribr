import shutil
import sqlite3
from pathlib import Path

from transcribr.store.db import connect
from transcribr.store.migrate import MIGRATIONS_DIR, migrate, schema_version

EARLIER = ("0001_initial.sql", "0002_failed_at.sql", "0003_caller_digits.sql")


def hits(conn: sqlite3.Connection, phrase: str) -> list[tuple[int, int]]:
    rows = conn.execute(
        "SELECT s.call_id, s.idx FROM segments_fts f JOIN segments s ON s.id = f.rowid"
        " WHERE segments_fts MATCH ? ORDER BY s.call_id, s.idx",
        (f'"{phrase}"',),
    )
    return [(r[0], r[1]) for r in rows]


def test_upgrading_a_database_with_speaker_labels(tmp_path: Path) -> None:
    before = tmp_path / "before"
    before.mkdir()
    for name in EARLIER:
        shutil.copy(MIGRATIONS_DIR / name, before / name)
    db = tmp_path / "transcribr.db"
    migrate(db, migrations_dir=before)
    conn = connect(db)
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (90000001, 'q', '2026-10-22 08:00:00',"
        " '2026-10-22T13:00:00Z', 2, '(405) 555-0142', 'y', 't', 'transcribed')"
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (90000001, 'en', 'small.en', 't')"
    )
    conn.executemany(
        "INSERT INTO segments (call_id, idx, start_s, end_s, speaker, text, words)"
        " VALUES (90000001, ?, ?, ?, ?, ?, '[]')",
        [
            (0, 0.0, 3.0, "Speaker 1", "Tire Pros, this is Nolan"),
            (1, 3.5, 7.0, "Speaker 2", "I need a three inch lift kit"),
        ],
    )
    conn.execute(
        "INSERT INTO speakers (call_id, label, speech_seconds, fingerprint)"
        " VALUES (90000001, 'Speaker 1', 3.0, x'00000000')"
    )
    conn.close()

    assert migrate(db)[0] == 4

    backups = list((tmp_path / "backups").glob("pre-migration-v3-*.db"))
    assert len(backups) == 1
    old = connect(backups[0])
    assert old.execute("SELECT count(*) FROM speakers").fetchone()[0] == 1
    old.close()

    conn = connect(db)
    assert schema_version(conn) == len(list(MIGRATIONS_DIR.glob("*.sql")))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "speakers" not in tables
    columns = {r[1] for r in conn.execute("PRAGMA table_info(segments)")}
    assert "speaker" not in columns
    assert "voiceprint" in columns
    rows = conn.execute("SELECT idx, text, voiceprint FROM segments ORDER BY idx").fetchall()
    assert [tuple(r) for r in rows] == [
        (0, "Tire Pros, this is Nolan", None),
        (1, "I need a three inch lift kit", None),
    ]
    assert hits(conn, "lift kit") == [(90000001, 1)]

    conn.execute(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text, voiceprint)"
        " VALUES (90000001, 2, 7.5, 9.0, 'what size tires', x'0000803f')"
    )
    assert hits(conn, "size tires") == [(90000001, 2)]
    conn.execute("DELETE FROM segments WHERE idx = 1")
    assert hits(conn, "lift kit") == []
