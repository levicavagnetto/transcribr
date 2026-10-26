import shutil
import sqlite3
from pathlib import Path

import pytest

from transcribr.store.db import connect
from transcribr.store.migrate import MIGRATIONS_DIR, migrate, schema_version

BEFORE = (
    "0001_initial.sql",
    "0002_failed_at.sql",
    "0003_caller_digits.sql",
    "0004_line_voiceprints.sql",
)
CALL = 90000001


def count(conn: sqlite3.Connection, table: str) -> int:
    value: int = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
    return value


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    """A database at version 4 with one transcribed call, then upgraded."""
    before = tmp_path / "before"
    before.mkdir()
    for name in BEFORE:
        shutil.copy(MIGRATIONS_DIR / name, before / name)
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
    old.executemany(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text, voiceprint)"
        " VALUES (?, ?, ?, ?, ?, x'0000803f')",
        [(CALL, 0, 0.0, 3.0, "Tire Pros, this is Nolan"), (CALL, 1, 3.5, 7.0, "a lift kit")],
    )
    old.close()

    assert migrate(db)[0] == 5
    assert len(list((tmp_path / "backups").glob("pre-migration-v4-*.db"))) == 1
    upgraded = connect(db)
    assert schema_version(upgraded) == len(list(MIGRATIONS_DIR.glob("*.sql")))
    return upgraded


def add_profile(conn: sqlite3.Connection, name: str = "Nolan") -> int:
    profile_id: int = conn.execute(
        "INSERT INTO profiles (display_name, created_at) VALUES (?, 't') RETURNING id", (name,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO name_variants (profile_id, variant, normalized) VALUES (?, ?, ?)",
        (profile_id, name, name.lower()),
    )
    conn.execute(
        "INSERT INTO voice_samples (profile_id, call_id, idx, added_at) VALUES (?, ?, 0, 't')",
        (profile_id, CALL),
    )
    conn.execute(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, updated_at)"
        " VALUES (?, ?, 'confident', 'auto', 'name', 't')",
        (CALL, profile_id),
    )
    return profile_id


def test_existing_transcripts_survive_and_the_new_tables_are_empty(
    conn: sqlite3.Connection,
) -> None:
    assert count(conn, "segments") == 2
    for table in ("profiles", "name_variants", "voice_samples", "attributions"):
        assert count(conn, table) == 0


def test_deleting_a_profile_takes_its_variants_samples_and_attributions(
    conn: sqlite3.Connection,
) -> None:
    nolan = add_profile(conn)
    other = add_profile(conn, "Dana")
    conn.execute("DELETE FROM profiles WHERE id = ?", (nolan,))
    for table in ("name_variants", "voice_samples", "attributions"):
        rows = conn.execute(f"SELECT profile_id FROM {table}").fetchall()  # noqa: S608
        assert [r[0] for r in rows] == [other], table
    assert count(conn, "segments") == 2  # the call itself is untouched


def test_retranscribing_a_call_drops_its_enrolled_lines_but_not_its_attributions(
    conn: sqlite3.Connection,
) -> None:
    add_profile(conn)
    conn.execute("DELETE FROM transcripts WHERE call_id = ?", (CALL,))
    assert count(conn, "voice_samples") == 0
    assert count(conn, "attributions") == 1


def test_deleting_a_call_drops_everything_about_it(conn: sqlite3.Connection) -> None:
    add_profile(conn)
    conn.execute("DELETE FROM calls WHERE id = ?", (CALL,))
    assert (count(conn, "voice_samples"), count(conn, "attributions")) == (0, 0)
    assert count(conn, "profiles") == 1


def test_a_sample_must_point_at_an_existing_line(conn: sqlite3.Connection) -> None:
    profile = add_profile(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO voice_samples (profile_id, call_id, idx, added_at) VALUES (?, ?, 9, 't')",
            (profile, CALL),
        )


def test_attribution_values_are_restricted(conn: sqlite3.Connection) -> None:
    profile = add_profile(conn)
    for column, value in (("status", "sure"), ("source", "guess"), ("method", "vibes")):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"UPDATE attributions SET {column} = ? WHERE profile_id = ?",  # noqa: S608
                (value, profile),
            )


def test_one_attribution_per_call_and_person_and_unique_variants(
    conn: sqlite3.Connection,
) -> None:
    profile = add_profile(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO attributions (call_id, profile_id, status, source, method, updated_at)"
            " VALUES (?, ?, 'maybe', 'auto', 'voice', 't')",
            (CALL, profile),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO name_variants (profile_id, variant, normalized)"
            " VALUES (?, 'NOLAN', 'nolan')",
            (profile,),
        )
