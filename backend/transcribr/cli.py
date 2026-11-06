"""Command-line entry point: `transcribr <command>`."""

import argparse
import logging
import os
import sqlite3
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from transcribr import __version__
from transcribr.data_cli import CliError, add_data_commands, run
from transcribr.logs import setup_command_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transcribr", description=__doc__)
    parser.add_argument("--version", action="version", version=f"transcribr {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    check = commands.add_parser(
        "ravon-check",
        help="log in to Ravon, list its queues and count one day's calls (no audio)",
    )
    check.add_argument(
        "--day",
        type=date.fromisoformat,
        default=None,
        help="day to count, YYYY-MM-DD (default: yesterday)",
    )
    check.add_argument(
        "--queue",
        action="append",
        dest="queues",
        help="queue value to count (repeatable; default: every queue Ravon lists)",
    )
    commands.add_parser("worker", help="run the worker service (polling and transcription)")
    commands.add_parser("reset-admin", help="remove the admin account and print a new setup code")
    commands.add_parser("web", help="run the web service (API and web app)")
    commands.add_parser(
        "worker-health", help="exit 0 if the worker's heartbeat is recent (Docker health check)"
    )
    commands.add_parser("backup", help="write a copy of the database to the backups folder")
    add_data_commands(commands)
    fetch = commands.add_parser("fetch-models", help="download and verify the speech models")
    fetch.add_argument(
        "--dest", type=Path, default=None, help="folder (default: TRANSCRIBR_MODELS_DIR)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 - one return per command
    # onnxruntime (used by faster-whisper) would otherwise send usage telemetry to Microsoft;
    # a running instance talks to Ravon only.
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command in {"calls", "people"}:
        return run(args, _data_database)
    if args.command in {"web", "worker"}:
        return _run_service(args.command)
    setup_command_logging()
    if args.command == "ravon-check":
        from transcribr.config import load_config  # noqa: PLC0415 - keep --help fast
        from transcribr.ravon_check import ravon_check  # noqa: PLC0415

        day = args.day or date.today() - timedelta(days=1)
        return ravon_check(load_config(), day=day, queues=args.queues, out=sys.stdout)
    if args.command == "reset-admin":
        return _reset_admin()
    if args.command == "worker-health":
        return _worker_health()
    if args.command == "backup":
        return _backup()
    if args.command == "fetch-models":
        from transcribr.config import load_config  # noqa: PLC0415
        from transcribr.models import ModelError, fetch_models, verify_models  # noqa: PLC0415

        logging.getLogger("transcribr").setLevel(logging.INFO)
        dest: Path = args.dest or load_config().models_dir
        try:
            fetch_models(dest)
        except ModelError as error:
            print(f"fetch-models failed: {error}", file=sys.stderr)
            return 1
        problems = verify_models(dest)
        for problem in problems:
            print(problem, file=sys.stderr)
        print("models verified" if not problems else "models are incomplete", file=sys.stderr)
        return 1 if problems else 0
    return 0


def _run_service(name: str) -> int:
    from transcribr.config import load_config  # noqa: PLC0415
    from transcribr.logs import setup_service_logging  # noqa: PLC0415

    config = load_config()
    setup_service_logging(name, config.data_dir)
    if name == "web":
        from transcribr.run_web import run_web  # noqa: PLC0415

        return run_web(config)
    from transcribr.run_worker import run_worker  # noqa: PLC0415

    return run_worker(config)


def _open_database() -> sqlite3.Connection | None:
    from transcribr.config import load_config  # noqa: PLC0415
    from transcribr.store.db import connect  # noqa: PLC0415

    path = load_config().database_path
    if not path.exists():
        print(f"There is no Transcribr database at {path}.", file=sys.stderr)
        return None
    return connect(path)


def _data_database() -> sqlite3.Connection:
    from transcribr.config import load_config  # noqa: PLC0415
    from transcribr.store.db import connect  # noqa: PLC0415

    path = load_config().database_path
    if not path.exists():
        raise CliError("no_database", f"There is no Transcribr database at {path}.")
    return connect(path)


def _worker_health() -> int:
    from transcribr.ops import WORKER_HEALTHY_WITHIN, heartbeat_age  # noqa: PLC0415
    from transcribr.timeutil import utcnow  # noqa: PLC0415

    conn = _open_database()
    if conn is None:
        return 1
    try:
        age = heartbeat_age(conn, utcnow())
    except sqlite3.Error as error:
        print(f"unhealthy: cannot read the heartbeat ({error})", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if age is None:
        print("unhealthy: the worker has not started yet", file=sys.stderr)
        return 1
    seconds = int(age.total_seconds())
    if age >= WORKER_HEALTHY_WITHIN:
        print(f"unhealthy: last worker heartbeat {seconds} s ago", file=sys.stderr)
        return 1
    print(f"healthy: last worker heartbeat {seconds} s ago")
    return 0


def _backup() -> int:
    from transcribr.config import load_config  # noqa: PLC0415
    from transcribr.ops import backup_database  # noqa: PLC0415
    from transcribr.timeutil import utcnow  # noqa: PLC0415

    conn = _open_database()
    if conn is None:
        return 1
    try:
        target = backup_database(conn, load_config().data_dir / "backups", utcnow())
    finally:
        conn.close()
    print(f"Backup written to {target}")
    return 0


def _reset_admin() -> int:
    from transcribr.admin import Admins  # noqa: PLC0415

    conn = _open_database()
    if conn is None:
        return 1
    code = Admins(conn).reset()
    print("The admin account and all admin sessions were removed.")
    print(f"New admin setup code: {code}")
    print("Open the web app, follow the Admin link in the top bar, and enter this code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
