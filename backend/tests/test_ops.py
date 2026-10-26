import shutil
import sqlite3
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from transcribr.admin import Admins
from transcribr.cli import main
from transcribr.ingest.uptime import Uptime
from transcribr.run_worker import start_heartbeat
from transcribr.settings import STORE_QUEUES, Settings
from transcribr.store.db import connect
from transcribr.store.migrate import migrate
from transcribr.store.state import LAST_POLL_OK, State
from transcribr.timeutil import to_iso, utcnow


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(folder))
    return folder


@pytest.fixture
def conn(data_dir: Path) -> Iterator[sqlite3.Connection]:
    migrate(data_dir / "transcribr.db")
    conn = connect(data_dir / "transcribr.db")
    yield conn
    conn.close()


# --- worker-health ----------------------------------------------------------


def test_worker_health_passes_with_a_recent_heartbeat(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    Uptime(conn).heartbeat(utcnow() - timedelta(seconds=30))
    assert main(["worker-health"]) == 0
    assert "healthy" in capsys.readouterr().out


def test_worker_health_fails_after_90_silent_seconds(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    Uptime(conn).heartbeat(utcnow() - timedelta(seconds=91))
    assert main(["worker-health"]) == 1
    assert "unhealthy: last worker heartbeat" in capsys.readouterr().err


def test_worker_health_fails_before_the_first_heartbeat(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["worker-health"]) == 1
    assert "has not started" in capsys.readouterr().err


def test_worker_health_fails_without_a_database(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["worker-health"]) == 1
    assert "no Transcribr database" in capsys.readouterr().err


def test_worker_health_fails_on_a_database_without_tables(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    connect(data_dir / "transcribr.db").close()
    assert main(["worker-health"]) == 1
    assert "cannot read the heartbeat" in capsys.readouterr().err


def test_the_heartbeat_thread_beats_while_the_main_loop_is_busy(
    conn: sqlite3.Connection, data_dir: Path
) -> None:
    stop = threading.Event()
    thread = start_heartbeat(data_dir / "transcribr.db", stop, interval=0.01)
    try:
        for _ in range(500):
            if conn.execute("SELECT count(*) FROM uptime_spans").fetchone()[0]:
                break
            stop.wait(0.01)
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert conn.execute("SELECT count(*) FROM uptime_spans").fetchone()[0] == 1


# --- backup and restore -----------------------------------------------------


def fill(conn: sqlite3.Connection) -> None:
    """Put rows in the main tables, including a transcript the search index picks up."""
    for rid in (1, 2, 3):
        conn.execute(
            "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
            " answered_by, listed_at, state) VALUES (?, 'q', '2026-10-22 08:00:00',"
            " '2026-10-22T13:00:00Z', 2, 'x', 'y', 't', 'transcribed')",
            (rid,),
        )
    conn.execute(
        "INSERT INTO jobs (type, call_id, created_at) VALUES ('transcribe', 3, ?)",
        (to_iso(utcnow()),),
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (1, 'en', 'small.en', 't')"
    )
    conn.execute(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text)"
        " VALUES (1, 0, 0, 2.5, 'thanks for calling about the tires')"
    )
    Settings(conn).set(STORE_QUEUES, ["tireProz-salescustserv"])
    State(conn).set(LAST_POLL_OK, to_iso(utcnow()))
    Uptime(conn).heartbeat(utcnow())
    admins = Admins(conn)
    admins.setup(admins.new_setup_code(), "admin", "a long enough passphrase")


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    # Table names come from sqlite_master, not from input.
    return {name: conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in tables}  # noqa: S608


def test_backup_restores_into_a_fresh_data_folder_with_identical_counts(
    conn: sqlite3.Connection, data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fill(conn)
    before = row_counts(conn)

    assert main(["backup"]) == 0
    out = capsys.readouterr().out
    backups = sorted((data_dir / "backups").glob("transcribr-*.db"))
    assert len(backups) == 1
    assert str(backups[0]) in out

    fresh = tmp_path / "fresh-data"
    fresh.mkdir()
    shutil.copy(backups[0], fresh / "transcribr.db")
    assert migrate(fresh / "transcribr.db") == []  # already at the current schema
    restored = connect(fresh / "transcribr.db")
    try:
        assert row_counts(restored) == before
        assert (
            restored.execute(
                "SELECT count(*) FROM segments_fts WHERE segments_fts MATCH 'tires'"
            ).fetchone()[0]
            == 1
        )
        assert Admins(restored).check_credentials("admin", "a long enough passphrase")
    finally:
        restored.close()


def test_two_backups_in_the_same_second_both_survive(
    conn: sqlite3.Connection, data_dir: Path
) -> None:
    assert main(["backup"]) == 0
    assert main(["backup"]) == 0
    assert len(list((data_dir / "backups").glob("transcribr-*.db"))) == 2


def test_backup_without_a_database_explains(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["backup"]) == 1
    assert "no Transcribr database" in capsys.readouterr().err
