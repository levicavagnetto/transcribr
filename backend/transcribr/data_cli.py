"""Data commands: `transcribr calls ...` and `transcribr people ...` (add-data-cli).

They work on the instance's database directly, in the web container, for people, scripts
and LLMs. They never contact Ravon. Text by default; `--json` prints exactly one JSON
document to stdout, errors included (design D6).
"""

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import date
from typing import Any, Protocol, TextIO

from transcribr.attribution.profiles import Profiles

CALL_STATES = ("not_transcribed", "waiting", "processing", "transcribed", "failed")
DEFAULT_LIMIT = 50

RUN = "docker compose exec web transcribr"


class CliError(Exception):
    """A not-found or invalid-input error, reported with exit code 1."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


Handler = Callable[[sqlite3.Connection, argparse.Namespace], tuple[Any, str]]
"""Returns (JSON value, text) for the command's output."""

HANDLERS: dict[tuple[str, str], Handler] = {}


class Subcommands(Protocol):
    """What argparse's add_subparsers() returns (its class is private)."""

    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


# --- parser -------------------------------------------------------------------


def _json_flag() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="print one JSON document")
    return parent


def _sub(
    group: Subcommands,
    name: str,
    summary: str,
    example: str,
) -> argparse.ArgumentParser:
    return group.add_parser(
        name,
        help=summary,
        description=summary,
        epilog=f"example:\n  {RUN} {example}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[_json_flag()],
    )


def _call_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--from",
        dest="start",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="first day, in the store's time zone",
    )
    parser.add_argument(
        "--to",
        dest="end",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="last day, inclusive",
    )
    parser.add_argument("--person", help="person's id or name (Confident or Maybe)")
    parser.add_argument(
        "--maybe", action="store_true", help="only calls with a Maybe (for --person, when given)"
    )
    parser.add_argument(
        "--unassigned", action="store_true", help="only transcribed calls with nobody attributed"
    )
    parser.add_argument("--state", choices=CALL_STATES, help="only calls in this state")
    parser.add_argument("--number", help="caller number, any punctuation")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"most calls to show (default {DEFAULT_LIMIT}; 0 for all)",
    )


def add_data_commands(commands: Subcommands) -> None:
    """Register `calls` and `people` on the top-level `transcribr` parser."""
    calls = commands.add_parser(
        "calls",
        help="list, search, read and transcribe calls",
        description="List, search, read and transcribe calls.",
    ).add_subparsers(dest="action", metavar="<action>", required=True)
    _call_filters(
        _sub(calls, "list", "list calls, newest first", "calls list --person Nolan --maybe --json")
    )
    search = _sub(
        calls,
        "search",
        "list calls whose transcript contains the words",
        'calls search "brake pads" --from 2026-11-01',
    )
    search.add_argument("words", help="words said in the call")
    _call_filters(search)
    show = _sub(
        calls, "show", "print a call's details and timestamped transcript", "calls show 1234"
    )
    show.add_argument("call_id", type=int, metavar="CALL_ID")
    transcribe = _sub(
        calls, "transcribe", "queue a Not transcribed or Failed call", "calls transcribe 1234"
    )
    transcribe.add_argument("call_id", type=int, metavar="CALL_ID")

    people = commands.add_parser(
        "people",
        help="list and add people; claim, confirm or reject calls",
        description="List and add people; claim, confirm or reject calls.",
    ).add_subparsers(dest="action", metavar="<action>", required=True)
    _sub(people, "list", "list people with their name variants and call counts", "people list")
    add = _sub(
        people,
        "add",
        "add a person and rematch every call",
        'people add "Nolan" --variant Nolan --variant Nolen',
    )
    add.add_argument("name", help="the person's display name")
    add.add_argument(
        "--variant",
        action="append",
        required=True,
        help="a spelling the transcript might contain (repeatable)",
    )
    for action, summary in (
        ("claim", "mark the call as this person's (Confident, set by hand)"),
        ("confirm", "turn this person's Maybe on the call into Confident"),
        ("reject", "mark the call as not this person's; matching won't add them back"),
    ):
        parser = _sub(people, action, summary, f"people {action} Nolan 1234")
        parser.add_argument("person", help="person's id or name")
        parser.add_argument("call_id", type=int, metavar="CALL_ID")


# --- shared lookups -------------------------------------------------------------


def require_call(conn: sqlite3.Connection, call_id: int) -> None:
    if conn.execute("SELECT 1 FROM calls WHERE id = ?", (call_id,)).fetchone() is None:
        raise CliError("call_not_found", f"No call {call_id} is listed.")


def find_person(conn: sqlite3.Connection, person: str) -> int:
    """A person's id from their id or their name, ignoring case (design D3)."""
    text = person.strip()
    if text.isdigit():
        if not Profiles(conn).exists(int(text)):
            raise CliError("person_not_found", f"No person has id {text}.")
        return int(text)
    rows = conn.execute(
        "SELECT id FROM profiles WHERE display_name = ? COLLATE NOCASE ORDER BY id", (text,)
    ).fetchall()
    if not rows:
        raise CliError("person_not_found", f"No person is named {text}.")
    if len(rows) > 1:
        ids = ", ".join(str(r["id"]) for r in rows)
        raise CliError(
            "person_ambiguous", f"More than one person is named {text} (ids {ids}); use an id."
        )
    return int(rows[0]["id"])


# --- running --------------------------------------------------------------------


def run(
    args: argparse.Namespace,
    open_database: Callable[[], sqlite3.Connection],
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    as_json: bool = args.json
    try:
        handler = HANDLERS.get((args.command, args.action))
        if handler is None:
            raise CliError("not_available", "This command is not built yet.")
        conn = open_database()
        try:
            value, text = handler(conn, args)
        except sqlite3.Error as error:
            raise CliError("database_error", f"Cannot read the database ({error}).") from None
        finally:
            conn.close()
    except CliError as error:
        print(error.message, file=err)
        if as_json:
            print(json.dumps({"error": error.code, "message": error.message}), file=out)
        return 1
    if as_json:
        print(json.dumps(value, ensure_ascii=False), file=out)
    else:
        print(text, file=out)
    return 0
