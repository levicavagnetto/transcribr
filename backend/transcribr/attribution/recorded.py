"""Recorded-message lines: the store's greeting and hold message, found from the transcripts (D2).

The same recording plays on every held call, so its lines repeat across many calls, cut off
wherever someone picks up. They are left out of the name window, so a greeting after the hold
message still counts. A line containing a name variant is never treated as recorded.
"""

import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from transcribr.attribution.names import Token, find_name, normalize

SHINGLE = 5  # words per n-gram
MIN_CALLS = 5  # an n-gram or short line must appear in this many calls to count as recorded
COVERAGE = 0.8  # share of a line's n-grams that must be common
SCAN_SECONDS = 180.0  # how much of each call is read to learn the recorded message


def _shingles(words: Sequence[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


@dataclass
class RecordedMessage:
    shingles: Counter[tuple[str, ...]] = field(default_factory=Counter[tuple[str, ...]])
    short_lines: Counter[str] = field(default_factory=Counter[str])

    @classmethod
    def learn(cls, calls: Iterable[Sequence[str]]) -> RecordedMessage:
        """Count, per call, the n-grams and short lines of each call's opening lines."""
        found = cls()
        for lines in calls:
            grams: set[tuple[str, ...]] = set()
            short: set[str] = set()
            for line in lines:
                words = normalize(line).split()
                if len(words) >= SHINGLE:
                    grams |= _shingles(words)
                elif words:
                    short.add(" ".join(words))
            found.shingles.update(grams)
            found.short_lines.update(short)
        return found

    def is_recorded(self, line: str, variants: Sequence[str] = ()) -> bool:
        """Whether a line is part of a recorded message. A line with a name is never one."""
        words = normalize(line).split()
        if not words:
            return False
        tokens = [Token(w, w, 0.0) for w in words]
        if variants and find_name(tokens, variants) is not None:
            return False
        if len(words) < SHINGLE:
            return self.short_lines[" ".join(words)] >= MIN_CALLS
        grams = [tuple(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)]
        common = sum(self.shingles[g] >= MIN_CALLS for g in grams)
        return common >= COVERAGE * len(grams)


def learn_from(conn: sqlite3.Connection) -> RecordedMessage:
    """Learn the recorded message from the opening of every transcribed call."""
    calls: dict[int, list[str]] = {}
    for call_id, text in conn.execute(
        "SELECT call_id, text FROM segments WHERE start_s < ? ORDER BY call_id, idx",
        (SCAN_SECONDS,),
    ):
        calls.setdefault(call_id, []).append(text)
    return RecordedMessage.learn(calls.values())
