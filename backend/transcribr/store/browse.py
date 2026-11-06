"""Reading calls for the call screens and API: filters, search, paging, detail, transcript."""

import base64
import binascii
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from transcribr.store.db import digits_only
from transcribr.store.state import QUEUE_LIST, State
from transcribr.timeutil import local_to_utc, to_iso

STATES = ("not_transcribed", "waiting", "processing", "transcribed", "failed")
# FTS5 snippet() markers around matched words; control characters never appear in transcripts.
_HIT_START, _HIT_END = "\x02", "\x03"
_SNIPPET_TOKENS = 16


class BadCursor(ValueError):
    pass


@dataclass(frozen=True)
class CallFilter:
    state: str | None = None
    since: datetime | None = None  # started at or after this moment (timezone-aware)
    start: date | None = None  # first day, in the store's time zone
    end: date | None = None  # last day, inclusive
    text: str | None = None  # words said in the call
    number: str | None = None  # caller number, any punctuation
    person: int | None = None  # attributed to this profile, Confident or Maybe
    maybe: bool = False  # has a Maybe attribution (to `person`, when one is given)
    unassigned: bool = False  # transcribed, and nobody is attributed


@dataclass
class CallPage:
    calls: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    next_cursor: str | None = None


def encode_cursor(start_utc: str, call_id: int) -> str:
    raw = json.dumps([start_utc, call_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        start_utc, call_id = json.loads(raw)
    except (binascii.Error, ValueError, TypeError) as error:
        raise BadCursor("That page cursor isn't valid; start from the first page.") from error
    if not isinstance(start_utc, str) or not isinstance(call_id, int):
        raise BadCursor("That page cursor isn't valid; start from the first page.")
    return start_utc, call_id


def fts_phrase(text: str) -> str | None:
    """The user's words as one FTS5 phrase, or None when there are no words to search for."""
    words = re.findall(r"\w+", text)
    return '"' + " ".join(words) + '"' if words else None


def passage_parts(snippet: str) -> list[dict[str, Any]]:
    """Split an FTS5 snippet into plain and matched runs, so the UI never renders HTML."""
    parts: list[dict[str, Any]] = []
    for piece in re.split(f"({_HIT_START}.*?{_HIT_END})", snippet):
        if not piece:
            continue
        hit = piece.startswith(_HIT_START)
        parts.append({"text": piece.strip(_HIT_START + _HIT_END), "hit": hit})
    return parts


def list_calls(
    conn: sqlite3.Connection, where: CallFilter, *, zone: str, limit: int, cursor: str | None
) -> CallPage:
    """Calls newest first. The cursor is the last row's (start, id), so pages stay put
    while new calls arrive above them."""
    conditions: list[str] = []
    params: list[Any] = []
    hits_cte = ""
    hits_join = ""
    hit_columns = ", NULL AS at_s, NULL AS snip"

    phrase = fts_phrase(where.text) if where.text else None
    if phrase is not None:
        # snippet() only works in a plain query on the FTS table, so the matches are
        # materialized first, then each call's earliest matching line is picked.
        # Fixed SQL; the user's words are a bound parameter.
        hits_cte = (
            "WITH matches AS MATERIALIZED (SELECT rowid AS segment_id,"  # noqa: S608
            f" snippet(segments_fts, 0, char(2), char(3), '…', {_SNIPPET_TOKENS}) AS snip"
            " FROM segments_fts WHERE segments_fts MATCH ?),"
            " hits AS (SELECT s.call_id AS call_id, s.start_s AS at_s, m.snip AS snip,"
            " row_number() OVER (PARTITION BY s.call_id ORDER BY s.idx) AS rn"
            " FROM matches m JOIN segments s ON s.id = m.segment_id) "
        )
        params.append(phrase)
        hits_join = " JOIN hits h ON h.call_id = c.id AND h.rn = 1"
        hit_columns = ", h.at_s AS at_s, h.snip AS snip"
    if where.state is not None:
        conditions.append("c.state = ?")
        params.append(where.state)
    if where.since is not None:
        conditions.append("c.start_utc >= ?")
        params.append(to_iso(where.since))
    if where.start is not None:
        conditions.append("c.start_utc >= ?")
        params.append(to_iso(local_to_utc(datetime.combine(where.start, time()), zone)))
    if where.end is not None:
        day_after = datetime.combine(where.end + timedelta(days=1), time())
        conditions.append("c.start_utc < ?")
        params.append(to_iso(local_to_utc(day_after, zone)))
    if where.number is not None:
        digits = digits_only(where.number)
        if digits:
            # A suffix match, so "555-0142" finds "(405) 555-0142".
            conditions.append("c.caller_digits LIKE '%' || ?")
            params.append(digits)
    people_conditions, people_params = _people_filter(where)
    conditions.extend(people_conditions)
    params.extend(people_params)
    if cursor is not None:
        start_utc, call_id = decode_cursor(cursor)
        conditions.append("(c.start_utc, c.id) < (?, ?)")
        params.extend([start_utc, call_id])

    # Only fixed fragments are joined here; every value is a bound parameter.
    sql = (
        hits_cte + "SELECT c.id, c.queue, c.start_local, c.start_utc, c.minutes,"  # noqa: S608
        " c.caller_number, c.answered_by, c.state,"
        " t.call_id IS NOT NULL AS has_transcript, coalesce(t.no_speech, 0) AS no_speech"
        + hit_columns
        + " FROM calls c LEFT JOIN transcripts t ON t.call_id = c.id"
        + hits_join
        + (" WHERE " + " AND ".join(conditions) if conditions else "")
        + " ORDER BY c.start_utc DESC, c.id DESC LIMIT ?"
    )
    params.append(limit + 1)
    rows = conn.execute(sql, params).fetchall()

    page = CallPage()
    for row in rows[:limit]:
        call = _call_row(row)
        call["passage"] = (
            {"at_s": row["at_s"], "parts": passage_parts(row["snip"])}
            if row["snip"] is not None
            else None
        )
        page.calls.append(call)
    people = attributions(conn, [c["id"] for c in page.calls])
    for call in page.calls:
        call["attributions"] = people.get(call["id"], [])
    if len(rows) > limit:
        last = rows[limit - 1]
        page.next_cursor = encode_cursor(last["start_utc"], last["id"])
    return page


_ATTRIBUTED_TO = (
    "EXISTS (SELECT 1 FROM attributions a WHERE a.call_id = c.id AND a.profile_id = ?"
    " AND a.status IN ('confident', 'maybe'))"
)
_MAYBE_FOR = (
    "EXISTS (SELECT 1 FROM attributions a WHERE a.call_id = c.id AND a.profile_id = ?"
    " AND a.status = 'maybe')"
)
_ANY_MAYBE = "EXISTS (SELECT 1 FROM attributions a WHERE a.call_id = c.id AND a.status = 'maybe')"


def _people_filter(where: CallFilter) -> tuple[list[str], list[Any]]:
    """The SQL conditions (fixed fragments) and parameters for the person filters."""
    conditions: list[str] = []
    params: list[Any] = []
    if where.person is not None:
        conditions.append(_MAYBE_FOR if where.maybe else _ATTRIBUTED_TO)
        params.append(where.person)
    elif where.maybe:
        conditions.append(_ANY_MAYBE)
    if where.unassigned:
        conditions.append("c.state = 'transcribed' AND NOT " + _ATTRIBUTED)
    return conditions, params


_ATTRIBUTED = (
    "EXISTS (SELECT 1 FROM attributions a WHERE a.call_id = c.id"
    " AND a.status IN ('confident', 'maybe'))"
)


def attributions(conn: sqlite3.Connection, call_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Each call's Confident and Maybe attributions; rejections are not shown."""
    found: dict[int, list[dict[str, Any]]] = {}
    if not call_ids:
        return found
    marks = ", ".join("?" for _ in call_ids)
    for r in conn.execute(
        "SELECT a.call_id, a.profile_id, p.display_name, a.status, a.method,"  # noqa: S608 - only "?" marks are joined in
        " a.name_heard, a.name_at_s"
        " FROM attributions a JOIN profiles p ON p.id = a.profile_id"
        f" WHERE a.call_id IN ({marks}) AND a.status IN ('confident', 'maybe')"
        " ORDER BY a.call_id, a.status, p.display_name COLLATE NOCASE",
        call_ids,
    ):
        found.setdefault(r["call_id"], []).append(
            {
                "profile_id": r["profile_id"],
                "display_name": r["display_name"],
                "status": r["status"],
                "method": r["method"],
                "name_heard": r["name_heard"],
                "name_at_s": r["name_at_s"],
            }
        )
    return found


def people_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Everyone's names and call counts, for the call list's People filters."""
    people = [
        {
            "id": r["id"],
            "display_name": r["display_name"],
            "calls": r["calls"],
            "maybe_calls": r["maybe_calls"],
        }
        for r in conn.execute(
            "SELECT p.id, p.display_name,"
            " count(a.call_id) FILTER (WHERE a.status IN ('confident', 'maybe')) AS calls,"
            " count(a.call_id) FILTER (WHERE a.status = 'maybe') AS maybe_calls"
            " FROM profiles p LEFT JOIN attributions a ON a.profile_id = p.id"
            " GROUP BY p.id ORDER BY p.display_name COLLATE NOCASE, p.id"
        )
    ]
    maybe: int = conn.execute(
        "SELECT count(DISTINCT call_id) FROM attributions WHERE status = 'maybe'"
    ).fetchone()[0]
    unassigned: int = conn.execute(
        f"SELECT count(*) FROM calls c WHERE c.state = 'transcribed' AND NOT {_ATTRIBUTED}"  # noqa: S608
    ).fetchone()[0]
    return {"people": people, "maybe_calls": maybe, "unassigned_calls": unassigned}


def _call_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "queue": row["queue"],
        "start_local": row["start_local"],
        "start_utc": row["start_utc"],
        "minutes": row["minutes"],
        "caller_number": row["caller_number"],
        "answered_by": row["answered_by"],
        "state": row["state"],
        "has_transcript": bool(row["has_transcript"]),
        "no_speech": bool(row["no_speech"]),
    }


def call_detail(conn: sqlite3.Connection, call_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT c.*, t.call_id IS NOT NULL AS has_transcript,"
        " coalesce(t.no_speech, 0) AS no_speech,"
        " t.transcribed_at, t.language, t.model"
        " FROM calls c LEFT JOIN transcripts t ON t.call_id = c.id WHERE c.id = ?",
        (call_id,),
    ).fetchone()
    if row is None:
        return None
    cached: dict[str, Any] | None = State(conn).get(QUEUE_LIST)
    labels = {q["value"]: q["label"] for q in cached["queues"]} if cached else {}
    return {
        **_call_row(row),
        "queue_label": labels.get(row["queue"]),
        "auto_queued": bool(row["auto_queued"]),
        "failure_reason": row["failure_reason"],
        "transcribed_at": row["transcribed_at"],
        "language": row["language"],
        "model": row["model"],
        "attributions": attributions(conn, [call_id]).get(call_id, []),
    }


def transcript(conn: sqlite3.Connection, call_id: int) -> dict[str, Any] | None:
    head = conn.execute(
        "SELECT call_id, language, model, transcribed_at, no_speech FROM transcripts"
        " WHERE call_id = ?",
        (call_id,),
    ).fetchone()
    if head is None:
        return None
    segments = [
        {
            "idx": r["idx"],
            "start_s": r["start_s"],
            "end_s": r["end_s"],
            "text": r["text"],
        }
        for r in conn.execute(
            "SELECT idx, start_s, end_s, text FROM segments WHERE call_id = ? ORDER BY idx",
            (call_id,),
        )
    ]
    return {
        "call_id": head["call_id"],
        "language": head["language"],
        "model": head["model"],
        "transcribed_at": head["transcribed_at"],
        "no_speech": bool(head["no_speech"]),
        "segments": segments,
    }
