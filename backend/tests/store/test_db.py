import sqlite3
from pathlib import Path

import pytest

from transcribr.store.db import connect, transaction


def test_connection_uses_wal_busy_timeout_and_foreign_keys(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_rows_are_addressable_by_name(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    row = conn.execute("SELECT 1 AS answer").fetchone()
    assert row["answer"] == 1


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE t (x INTEGER)")
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 1


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE t (x INTEGER)")
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("boom")
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 0


def test_two_connections_see_each_others_writes(tmp_path: Path) -> None:
    writer = connect(tmp_path / "t.db")
    reader = connect(tmp_path / "t.db")
    writer.execute("CREATE TABLE t (x INTEGER)")
    with transaction(writer):
        writer.execute("INSERT INTO t VALUES (7)")
    assert reader.execute("SELECT x FROM t").fetchone()[0] == 7


def test_connect_creates_missing_parent_folder(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nested" / "dir" / "t.db")
    assert isinstance(conn, sqlite3.Connection)
    assert (tmp_path / "nested" / "dir" / "t.db").exists()
