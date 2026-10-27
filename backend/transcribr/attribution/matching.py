"""Attribution rows in the database: automatic matching, manual decisions and rematching.

Automatic matching reads stored transcript words and line voiceprints only, so it never needs
the audio, Ravon or a model (design D6). It deletes and rewrites `source = 'auto'` rows only;
manual rows are never touched by it.
"""

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from transcribr.attribution.names import find_name, opening
from transcribr.attribution.profiles import ProfileError, Profiles
from transcribr.attribution.rules import Decision, Evidence, decide
from transcribr.attribution.voice import (
    Vector,
    VoiceSamples,
    call_prints,
    line_scores,
    presence_score,
)
from transcribr.settings import VOICE_HIGH, VOICE_LOW, Settings
from transcribr.store.db import transaction
from transcribr.timeutil import to_iso, utcnow

log = logging.getLogger(__name__)

REMATCH_SETTINGS = frozenset({VOICE_LOW.key, VOICE_HIGH.key})


@dataclass(frozen=True)
class MatchContext:
    """Everything about the people that matching needs, read once per job."""

    variants: dict[int, tuple[str, ...]]
    voices: dict[int, Vector]  # usable voice profiles only
    low: float
    high: float


def load_context(conn: sqlite3.Connection) -> MatchContext:
    settings = Settings(conn)
    return MatchContext(
        {p.id: p.variants for p in Profiles(conn).everyone()},
        VoiceSamples(conn).usable_voices(),
        settings.get(VOICE_LOW),
        settings.get(VOICE_HIGH),
    )


def _call_words(conn: sqlite3.Connection, call_id: int) -> list[tuple[float, str]]:
    """(start, word) for every word of a call; a line without word times uses its start."""
    words: list[tuple[float, str]] = []
    for r in conn.execute(
        "SELECT start_s, text, words FROM segments WHERE call_id = ? ORDER BY idx", (call_id,)
    ):
        timed: list[list[object]] = json.loads(r["words"] or "[]")
        if timed:
            words.extend((float(str(w[0])), str(w[2])) for w in timed)
        else:
            words.extend((r["start_s"], word) for word in str(r["text"]).split())
    return words


def attribute_call(
    conn: sqlite3.Connection, call_id: int, context: MatchContext, now: datetime
) -> list[Decision]:
    """Rewrite one call's automatic attributions. The caller holds the write transaction."""
    tokens = opening(_call_words(conn, call_id))
    prints = call_prints(conn, call_id)
    evidence = {
        profile_id: Evidence(
            find_name(tokens, variants),
            profile_id in context.voices,
            presence_score(line_scores(prints, context.voices[profile_id]))
            if profile_id in context.voices
            else None,
        )
        for profile_id, variants in context.variants.items()
    }
    manual = {
        r[0]
        for r in conn.execute(
            "SELECT profile_id FROM attributions WHERE call_id = ? AND source = 'manual'",
            (call_id,),
        )
    }
    decisions = decide(evidence, low=context.low, high=context.high, manual=manual)
    conn.execute("DELETE FROM attributions WHERE call_id = ? AND source = 'auto'", (call_id,))
    conn.executemany(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, name_heard,"
        " name_at_s, voice_score, updated_at) VALUES (?, ?, ?, 'auto', ?, ?, ?, ?, ?)",
        [
            (
                call_id,
                d.profile_id,
                d.status,
                d.method,
                d.name.heard if d.name else None,
                d.name.at_s if d.name else None,
                d.voice_score,
                to_iso(now),
            )
            for d in decisions
        ],
    )
    return decisions


def rematch_all(conn: sqlite3.Connection, now: datetime) -> int:
    """Recompute automatic attributions for every transcribed call; returns how many.

    Each call is its own short transaction, so the web service is never kept waiting.
    """
    context = load_context(conn)
    call_ids = [
        r[0] for r in conn.execute("SELECT call_id FROM transcripts ORDER BY call_id").fetchall()
    ]
    for call_id in call_ids:
        with transaction(conn):
            if conn.execute("SELECT 1 FROM transcripts WHERE call_id = ?", (call_id,)).fetchone():
                attribute_call(conn, call_id, context, now)
    return len(call_ids)


class Attributions:
    """Manual decisions by anyone on the shop network: claim, reject, confirm a Maybe."""

    def __init__(self, conn: sqlite3.Connection, *, now: Callable[[], datetime] = utcnow) -> None:
        self._conn = conn
        self._now = now

    def claim(self, call_id: int, profile_id: int) -> None:
        """The call is this person's: Confident, method manual (keeping any evidence found)."""
        self._manual(call_id, profile_id, "confident")

    def reject(self, call_id: int, profile_id: int) -> None:
        """The call is not this person's; automatic matching won't add them back."""
        self._manual(call_id, profile_id, "rejected")

    def confirm(self, call_id: int, profile_id: int) -> None:
        """A Maybe for this person becomes Confident, method manual."""
        with transaction(self._conn):
            row = self._conn.execute(
                "SELECT status FROM attributions WHERE call_id = ? AND profile_id = ?",
                (call_id, profile_id),
            ).fetchone()
            if row is None or row["status"] != "maybe":
                raise ProfileError("not_maybe", "Only a Maybe can be confirmed.")
            self._conn.execute(
                "UPDATE attributions SET status = 'confident', source = 'manual',"
                " method = 'manual', updated_at = ? WHERE call_id = ? AND profile_id = ?",
                (to_iso(self._now()), call_id, profile_id),
            )

    def _manual(self, call_id: int, profile_id: int, status: str) -> None:
        with transaction(self._conn):
            if (
                self._conn.execute("SELECT 1 FROM calls WHERE id = ?", (call_id,)).fetchone()
                is None
            ):
                raise ProfileError("call_not_found", "There is no such call.")
            Profiles(self._conn).get(profile_id)
            self._conn.execute(
                "INSERT INTO attributions (call_id, profile_id, status, source, method, updated_at)"
                " VALUES (?, ?, ?, 'manual', 'manual', ?)"
                " ON CONFLICT (call_id, profile_id) DO UPDATE SET status = excluded.status,"
                " source = 'manual', method = 'manual', updated_at = excluded.updated_at",
                (call_id, profile_id, status, to_iso(self._now())),
            )
