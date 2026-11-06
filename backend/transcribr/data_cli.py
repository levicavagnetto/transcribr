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

from transcribr.attribution.matching import Attributions
from transcribr.attribution.profiles import Profile, ProfileError, Profiles
from transcribr.settings import TIME_ZONE, Settings
from transcribr.store.browse import (
    CallFilter,
    attributions,
    call_detail,
    fts_phrase,
    list_calls,
    people_counts,
    transcript,
)
from transcribr.store.calls import request_transcription
from transcribr.timeutil import utcnow

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
        handler = HANDLERS[(args.command, args.action)]
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


# --- calls ---------------------------------------------------------------------

STATE_LABELS = {
    "not_transcribed": "Not transcribed",
    "waiting": "Queued",
    "processing": "Transcribing",
    "transcribed": "Transcribed",
    "failed": "Failed",
}
STATUS_LABELS = {"confident": "Confident", "maybe": "Maybe"}
METHOD_LABELS = {"name": "by name", "manual": "set by hand"}


def clock(seconds: float) -> str:
    """Seconds as m:ss, as in the web app."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _people_text(attributions: list[dict[str, Any]]) -> str:
    if not attributions:
        return "nobody"
    return ", ".join(
        f"{a['display_name']} ({STATUS_LABELS[a['status']]}, {METHOD_LABELS[a['method']]})"
        for a in attributions
    )


def _call_line(call: dict[str, Any]) -> str:
    return (
        f"#{call['id']}  {call['start_local']}  {call['caller_number'] or 'unknown number'}"
        f"  {call['minutes']:g} min  {STATE_LABELS[call['state']]}"
        f"  people: {_people_text(call['attributions'])}"
    )


def _filter(conn: sqlite3.Connection, args: argparse.Namespace, text: str | None) -> CallFilter:
    if args.unassigned and (args.person is not None or args.maybe):
        raise CliError("invalid_filter", "--unassigned can't be combined with --person or --maybe.")
    if args.limit < 0:
        raise CliError("invalid_limit", "--limit must be 0 (all) or more.")
    return CallFilter(
        state=args.state,
        start=args.start,
        end=args.end,
        text=text,
        number=args.number,
        person=find_person(conn, args.person) if args.person is not None else None,
        maybe=args.maybe,
        unassigned=args.unassigned,
    )


def _calls(
    conn: sqlite3.Connection, args: argparse.Namespace, text: str | None
) -> list[dict[str, Any]]:
    where = _filter(conn, args, text)
    limit = args.limit or conn.execute("SELECT count(*) FROM calls").fetchone()[0] or 1
    page = list_calls(conn, where, zone=Settings(conn).get(TIME_ZONE), limit=limit, cursor=None)
    return page.calls


def calls_list(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    calls = _calls(conn, args, None)
    for call in calls:
        del call["passage"]
    text = "\n".join(_call_line(c) for c in calls) or "No calls match."
    return {"calls": calls}, text


def calls_search(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    if fts_phrase(args.words) is None:
        raise CliError("invalid_search", "Give at least one word to search for.")
    calls = _calls(conn, args, args.words)
    lines: list[str] = []
    for call in calls:
        passage = call.pop("passage")
        call["match"] = {
            "at_s": passage["at_s"],
            "text": "".join(p["text"] for p in passage["parts"]),
        }
        lines.append(_call_line(call))
        lines.append(f"    [{clock(passage['at_s'])}] {call['match']['text']}")
    return {"calls": calls}, "\n".join(lines) or "No calls match."


def calls_show(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    detail = call_detail(conn, args.call_id)
    if detail is None:
        raise CliError("call_not_found", f"No call {args.call_id} is listed.")
    lines = [
        f"Call #{detail['id']}",
        f"Time: {detail['start_local']}",
        f"Caller: {detail['caller_number'] or 'unknown number'}",
        f"Queue: {detail['queue_label'] or detail['queue']}",
        f"Answered by (Ravon): {detail['answered_by'] or 'unknown'}",
        f"Length: {detail['minutes']:g} min",
        f"State: {STATE_LABELS[detail['state']]}",
        f"People: {_people_text(detail['attributions'])}",
        "",
    ]
    lines.extend(_people_hits(detail["attributions"]))
    words = transcript(conn, args.call_id)
    if words is None:
        lines.append("No transcript yet.")
    elif words["no_speech"] or not words["segments"]:
        lines.append("Transcribed, but no speech was found.")
    else:
        lines.extend(f"[{clock(s['start_s'])}] {s['text']}" for s in words["segments"])
    return {"call": detail, "transcript": words}, "\n".join(lines).rstrip()


def _people_hits(attributions: list[dict[str, Any]]) -> list[str]:
    hits = [
        f"{a['display_name']}: heard {a['name_heard']!r} at {clock(a['name_at_s'])}"
        for a in attributions
        if a["name_heard"] and a["name_at_s"] is not None
    ]
    return [*hits, ""] if hits else []


def calls_transcribe(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    require_call(conn, args.call_id)
    queued = request_transcription(conn, args.call_id, utcnow())
    state = conn.execute("SELECT state FROM calls WHERE id = ?", (args.call_id,)).fetchone()[0]
    label = STATE_LABELS[state]
    text = (
        f"Call #{args.call_id} is queued for transcription."
        if queued
        else f"Call #{args.call_id} was left alone; it is {label}."
    )
    return {"call_id": args.call_id, "queued": queued, "state": state}, text


HANDLERS.update(
    {
        ("calls", "list"): calls_list,
        ("calls", "search"): calls_search,
        ("calls", "show"): calls_show,
        ("calls", "transcribe"): calls_transcribe,
    }
)


# --- people --------------------------------------------------------------------


def _person_json(profile: Profile, counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "variants": list(profile.variants),
        "calls": counts.get("calls", 0),
        "maybe_calls": counts.get("maybe_calls", 0),
    }


def _person_line(person: dict[str, Any]) -> str:
    return (
        f"#{person['id']}  {person['display_name']}  (heard as: {', '.join(person['variants'])})"
        f"  {person['calls']} calls, {person['maybe_calls']} still Maybe"
    )


def _counts(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    return {p["id"]: p for p in people_counts(conn)["people"]}


def people_list(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    del args
    counts = _counts(conn)
    people = [_person_json(p, counts.get(p.id, {})) for p in Profiles(conn).everyone()]
    text = "\n".join(_person_line(p) for p in people) or "Nobody has been added yet."
    return {"people": people}, text


def people_add(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Any, str]:
    try:
        profile = Profiles(conn).create(args.name, args.variant)
    except ProfileError as error:
        raise CliError(error.code, error.message) from None
    person = _person_json(profile, {})
    return {"person": person}, (
        f"Added #{profile.id} {profile.display_name}. Every call will be rematched shortly."
    )


def _decide(conn: sqlite3.Connection, args: argparse.Namespace, done: str) -> tuple[Any, str]:
    profile_id = find_person(conn, args.person)
    require_call(conn, args.call_id)
    try:
        getattr(Attributions(conn), args.action)(args.call_id, profile_id)
    except ProfileError as error:
        raise CliError(error.code, error.message) from None
    people = attributions(conn, [args.call_id]).get(args.call_id, [])
    name = Profiles(conn).get(profile_id).display_name
    text = f"{name} {done} call #{args.call_id}.\nPeople: {_people_text(people)}"
    return {"call_id": args.call_id, "attributions": people}, text


HANDLERS.update(
    {
        ("people", "list"): people_list,
        ("people", "add"): people_add,
        ("people", "claim"): lambda conn, args: _decide(conn, args, "is now Confident on"),
        ("people", "confirm"): lambda conn, args: _decide(conn, args, "is now Confident on"),
        ("people", "reject"): lambda conn, args: _decide(conn, args, "is marked as not on"),
    }
)
