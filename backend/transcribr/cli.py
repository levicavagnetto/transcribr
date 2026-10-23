"""Command-line entry point: `transcribr <command>`."""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import date, timedelta

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
    return parser


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)


def main(argv: Sequence[str] | None = None) -> int:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
