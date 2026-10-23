"""Command-line entry point: `transcribr <command>`."""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from transcribr import __version__
from transcribr.redaction import RedactingFormatter


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
    fetch = commands.add_parser("fetch-models", help="download and verify the speech models")
    fetch.add_argument(
        "--dest", type=Path, default=None, help="folder (default: TRANSCRIBR_MODELS_DIR)"
    )
    return parser


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911 - one return per command
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    _setup_logging()
    if args.command == "ravon-check":
        from transcribr.config import load_config  # noqa: PLC0415 - keep --help fast
        from transcribr.ravon_check import ravon_check  # noqa: PLC0415

        day = args.day or date.today() - timedelta(days=1)
        return ravon_check(load_config(), day=day, queues=args.queues, out=sys.stdout)
    if args.command == "worker":
        from transcribr.config import load_config  # noqa: PLC0415
        from transcribr.run_worker import run_worker  # noqa: PLC0415

        logging.getLogger("transcribr").setLevel(logging.INFO)
        return run_worker(load_config())
    if args.command == "reset-admin":
        return _reset_admin()
    if args.command == "web":
        from transcribr.run_web import run_web  # noqa: PLC0415

        logging.getLogger("transcribr").setLevel(logging.INFO)
        return run_web()
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


def _reset_admin() -> int:
    from transcribr.admin import Admins  # noqa: PLC0415
    from transcribr.config import load_config  # noqa: PLC0415
    from transcribr.store.db import connect  # noqa: PLC0415

    config = load_config()
    if not config.database_path.exists():
        print(f"There is no Transcribr database at {config.database_path}.", file=sys.stderr)
        return 1
    code = Admins(connect(config.database_path)).reset()
    print("The admin account and all admin sessions were removed.")
    print(f"New admin setup code: {code}")
    print("Open the web app, follow the footer Admin link, and enter this code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
