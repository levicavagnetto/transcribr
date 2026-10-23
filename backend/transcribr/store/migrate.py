"""Schema migrations: numbered SQL files tracked with PRAGMA user_version."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from transcribr.store.db import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def _migration_files(folder: Path) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(folder.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            raise MigrationError(f"badly named migration file: {path.name}")
        found.append((int(match.group(1)), path))
    for expected, (number, path) in enumerate(found, start=1):
        if number != expected:
            raise MigrationError(f"gap in migrations: expected {expected:04d}, found {path.name}")
    return found


def _backup(conn: sqlite3.Connection, backup_dir: Path, version: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"pre-migration-v{version}-{stamp}.db"
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)
    finally:
        copy.close()
    return target


def migrate(
    db_path: Path,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    backup_dir: Path | None = None,
) -> list[int]:
    """Apply pending migrations in order and return the numbers applied.

    An existing database is backed up first. Each migration runs in its own
    transaction together with its version bump, so a failure leaves the data
    and the version exactly as they were.
    """
    files = _migration_files(migrations_dir)
    conn = connect(db_path)
    try:
        current = schema_version(conn)
        if current > len(files):
            raise MigrationError(
                f"database is at version {current}, newer than this code ({len(files)})"
            )
        pending = files[current:]
        if not pending:
            return []
        if current > 0:
            _backup(conn, backup_dir or db_path.parent / "backups", current)
        applied: list[int] = []
        for number, path in pending:
            sql = path.read_text(encoding="utf-8")
            try:
                conn.executescript(
                    f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;"
                )
            except sqlite3.Error as error:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise MigrationError(f"{path.name} failed: {error}") from error
            applied.append(number)
        return applied
    finally:
        conn.close()
