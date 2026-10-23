from pathlib import Path

import pytest

from transcribr.store.db import connect
from transcribr.store.migrate import MigrationError, migrate, schema_version


def write(folder: Path, name: str, sql: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(sql, encoding="utf-8")


def test_fresh_database_gets_every_migration_and_no_backup(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    write(migrations, "0002_second.sql", "CREATE TABLE b (y INTEGER);")
    db = tmp_path / "data" / "transcribr.db"

    applied = migrate(db, migrations_dir=migrations, backup_dir=tmp_path / "backups")

    assert applied == [1, 2]
    conn = connect(db)
    assert schema_version(conn) == 2
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"a", "b"} <= tables
    assert not (tmp_path / "backups").exists()


def test_upgrade_applies_only_new_migrations_and_keeps_a_backup(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    backups = tmp_path / "backups"
    db = tmp_path / "transcribr.db"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    migrate(db, migrations_dir=migrations, backup_dir=backups)
    conn = connect(db)
    conn.execute("INSERT INTO a VALUES (42)")

    write(migrations, "0002_second.sql", "ALTER TABLE a ADD COLUMN note TEXT;")
    applied = migrate(db, migrations_dir=migrations, backup_dir=backups)

    assert applied == [2]
    assert schema_version(connect(db)) == 2
    copies = list(backups.glob("*.db"))
    assert len(copies) == 1
    assert "v1" in copies[0].name
    old = connect(copies[0])
    assert schema_version(old) == 1
    assert old.execute("SELECT x FROM a").fetchone()[0] == 42


def test_nothing_to_do_makes_no_backup(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    backups = tmp_path / "backups"
    db = tmp_path / "transcribr.db"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    migrate(db, migrations_dir=migrations, backup_dir=backups)

    assert migrate(db, migrations_dir=migrations, backup_dir=backups) == []
    assert not backups.exists()


def test_failing_migration_leaves_data_and_version_unchanged(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    db = tmp_path / "transcribr.db"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    migrate(db, migrations_dir=migrations, backup_dir=tmp_path / "backups")
    connect(db).execute("INSERT INTO a VALUES (1)")

    # The first two statements would succeed on their own; the third fails, so none may stick.
    write(
        migrations,
        "0002_broken.sql",
        "CREATE TABLE b (y INTEGER);\nINSERT INTO a VALUES (2);\nTHIS IS NOT SQL;",
    )
    with pytest.raises(MigrationError, match=r"0002_broken\.sql"):
        migrate(db, migrations_dir=migrations, backup_dir=tmp_path / "backups")

    conn = connect(db)
    assert schema_version(conn) == 1
    assert [r[0] for r in conn.execute("SELECT x FROM a")] == [1]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "b" not in tables


def test_migration_files_must_be_numbered_without_gaps(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    write(migrations, "0003_third.sql", "CREATE TABLE c (z INTEGER);")
    with pytest.raises(MigrationError, match="gap"):
        migrate(tmp_path / "t.db", migrations_dir=migrations, backup_dir=tmp_path / "b")


def test_database_newer_than_the_code_is_refused(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    write(migrations, "0001_first.sql", "CREATE TABLE a (x INTEGER);")
    db = tmp_path / "t.db"
    connect(db).execute("PRAGMA user_version = 5")
    with pytest.raises(MigrationError, match="newer"):
        migrate(db, migrations_dir=migrations, backup_dir=tmp_path / "b")
