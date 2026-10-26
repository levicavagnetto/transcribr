import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from transcribr.ravon.parse import Recording
from transcribr.store.calls import add_listed
from transcribr.store.db import connect, digits_only
from transcribr.store.migrate import MIGRATIONS_DIR, migrate, schema_version


@pytest.mark.parametrize(
    ("raw", "digits"),
    [
        ("(405) 555-0142", "4055550142"),
        ("405.555.0142", "4055550142"),
        ("+1 405 555 0142", "14055550142"),
        ("Anonymous", ""),
        ("", ""),
    ],
)
def test_digits_only(raw: str, digits: str) -> None:
    assert digits_only(raw) == digits


def test_the_migration_fills_in_existing_calls(tmp_path: Path) -> None:
    before = tmp_path / "before"
    before.mkdir()
    for name in ("0001_initial.sql", "0002_failed_at.sql"):
        shutil.copy(MIGRATIONS_DIR / name, before / name)
    db = tmp_path / "transcribr.db"
    migrate(db, migrations_dir=before)
    conn = connect(db)
    for rid, caller in ((90000001, "(405) 555-0142"), (90000002, "Anonymous")):
        conn.execute(
            "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
            " answered_by, listed_at) VALUES (?, 'q', '2026-10-22 08:00:00',"
            " '2026-10-22T13:00:00Z', 2, ?, 'y', 't')",
            (rid, caller),
        )
    conn.close()

    migrate(db)

    conn = connect(db)
    assert schema_version(conn) == len(list(MIGRATIONS_DIR.glob("*.sql")))
    rows = conn.execute("SELECT id, caller_digits FROM calls ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(90000001, "4055550142"), (90000002, "")]


def test_newly_listed_calls_store_their_digits(tmp_path: Path) -> None:
    migrate(tmp_path / "t.db")
    conn = connect(tmp_path / "t.db")
    add_listed(
        conn,
        Recording(90000003, "2026-10-22 08:00:00", 2.0, "(580) 555-0119", "SW Counter Sales"),
        queue="q",
        zone="America/Chicago",
        now=datetime(2026, 10, 22, 14, tzinfo=UTC),
        auto_queue=False,
    )
    assert conn.execute("SELECT caller_digits FROM calls").fetchone()[0] == "5805550119"
