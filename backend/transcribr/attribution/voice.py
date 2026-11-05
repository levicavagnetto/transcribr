"""Voice profiles from enrolled transcript lines, and voice presence in a call (design D3, D5).

Only the admin enrolls lines. A profile's centroid is the L2-normalized, duration-weighted mean
of its enrolled lines' voiceprints, computed from the current samples whenever it is needed.
Scoring centers every voiceprint on the instance mean first: all lines share a large phone
channel component that otherwise makes everyone look alike.
Voiceprints, centroids and line scores never leave this module through the API.
"""

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

from transcribr.attribution.profiles import ProfileError, Profiles
from transcribr.attribution.queue import request_rematch
from transcribr.store.db import transaction
from transcribr.timeutil import to_iso, utcnow

type Vector = npt.NDArray[np.float32]

# MIN_PRESENCE_SECONDS set by calibration on 2026-11-05 (design D9); the usability rule kept.
MIN_CALLS = 3
MIN_SECONDS = 30.0
MIN_PRESENCE_SECONDS = 2.0


def from_blob(blob: bytes) -> Vector:
    return np.frombuffer(blob, dtype=np.float32)


@dataclass(frozen=True)
class VoiceProgress:
    calls: int
    seconds: float

    @property
    def usable(self) -> bool:
        return self.calls >= MIN_CALLS and self.seconds >= MIN_SECONDS

    @property
    def calls_needed(self) -> int:
        return max(0, MIN_CALLS - self.calls)

    @property
    def seconds_needed(self) -> float:
        return max(0.0, MIN_SECONDS - self.seconds)


@dataclass(frozen=True)
class EnrolledLine:
    idx: int
    start_s: float
    end_s: float


@dataclass(frozen=True)
class EnrolledCall:
    call_id: int
    start_local: str
    lines: tuple[EnrolledLine, ...]

    @property
    def seconds(self) -> float:
        return sum(line.end_s - line.start_s for line in self.lines)


def centroid(prints: Sequence[tuple[Vector, float]]) -> Vector | None:
    """The duration-weighted mean of (voiceprint, seconds) pairs, at unit length."""
    if not prints:
        return None
    weights = np.array([seconds for _, seconds in prints], dtype=np.float64)
    mean = np.average(np.stack([vp for vp, _ in prints]), axis=0, weights=weights)
    norm = float(np.linalg.norm(mean))
    if norm == 0.0:
        return None
    return (mean / norm).astype(np.float32)


def instance_mean(conn: sqlite3.Connection) -> Vector | None:
    """The duration-weighted mean of every stored line voiceprint (not unit length)."""
    total: npt.NDArray[np.float64] | None = None
    weight = 0.0
    for blob, seconds in conn.execute(
        "SELECT voiceprint, end_s - start_s FROM segments WHERE voiceprint IS NOT NULL"
    ):
        vp = from_blob(blob).astype(np.float64) * seconds
        total = vp if total is None else total + vp
        weight += seconds
    if total is None or weight <= 0.0:
        return None
    return (total / weight).astype(np.float32)


def centered(
    prints: Sequence[tuple[Vector, float]], mean: Vector | None
) -> list[tuple[Vector, float]]:
    """Each voiceprint minus the instance mean, back at unit length; unchanged without a mean."""
    if mean is None:
        return list(prints)
    out: list[tuple[Vector, float]] = []
    for vp, seconds in prints:
        diff = vp - mean
        norm = float(np.linalg.norm(diff))
        if norm > 1e-6:
            out.append(((diff / norm).astype(np.float32), seconds))
    return out


def presence_score(
    lines: Sequence[tuple[float, float]], min_presence: float = MIN_PRESENCE_SECONDS
) -> float | None:
    """How strongly a voice is present in a call, from its lines' (seconds, score) pairs.

    The highest score s at which the lines scoring s or more add up to at least min_presence
    seconds. None when the call has less voiceprinted speech than that.
    """
    total = 0.0
    for seconds, score in sorted(lines, key=lambda line: line[1], reverse=True):
        total += seconds
        if total >= min_presence:
            return score
    return None


def band(score: float | None, low: float, high: float) -> str | None:
    """'strong', 'weak' or None for a presence score against the instance's thresholds."""
    if score is None or score < low:
        return None
    return "strong" if score >= high else "weak"


def line_scores(prints: Sequence[tuple[Vector, float]], voice: Vector) -> list[tuple[float, float]]:
    """(seconds, cosine similarity) for each (voiceprint, seconds); both are unit length."""
    return [(seconds, float(np.dot(vp, voice))) for vp, seconds in prints]


class VoiceSamples:
    def __init__(self, conn: sqlite3.Connection, *, now: Callable[[], datetime] = utcnow) -> None:
        self._conn = conn
        self._now = now

    def add(self, profile_id: int, call_id: int, lines: Sequence[int]) -> VoiceProgress:
        """Enroll a call's lines for a person. Lines already enrolled are kept once."""
        wanted = sorted(set(lines))
        if not wanted:
            raise ProfileError("no_lines", "Tick at least one line to enroll.")
        with transaction(self._conn):
            Profiles(self._conn).get(profile_id)
            self._check_lines(call_id, wanted)
            self._conn.executemany(
                "INSERT INTO voice_samples (profile_id, call_id, idx, added_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                [(profile_id, call_id, idx, to_iso(self._now())) for idx in wanted],
            )
            request_rematch(self._conn, self._now())
        return self.progress(profile_id)

    def remove_call(self, profile_id: int, call_id: int) -> VoiceProgress:
        """Take one call's enrolled lines out of a person's voice profile."""
        with transaction(self._conn):
            Profiles(self._conn).get(profile_id)
            self._conn.execute(
                "DELETE FROM voice_samples WHERE profile_id = ? AND call_id = ?",
                (profile_id, call_id),
            )
            request_rematch(self._conn, self._now())
        return self.progress(profile_id)

    def progress(self, profile_id: int) -> VoiceProgress:
        row = self._conn.execute(
            "SELECT count(DISTINCT v.call_id), coalesce(sum(s.end_s - s.start_s), 0.0)"
            " FROM voice_samples v JOIN segments s USING (call_id, idx) WHERE v.profile_id = ?",
            (profile_id,),
        ).fetchone()
        return VoiceProgress(row[0], float(row[1]))

    def enrolled(self, profile_id: int) -> list[EnrolledCall]:
        """A person's enrolled lines, grouped by call, newest call first."""
        calls: dict[int, EnrolledCall] = {}
        for r in self._conn.execute(
            "SELECT v.call_id, c.start_local, s.idx, s.start_s, s.end_s FROM voice_samples v"
            " JOIN segments s USING (call_id, idx) JOIN calls c ON c.id = v.call_id"
            " WHERE v.profile_id = ? ORDER BY c.start_utc DESC, v.call_id, s.idx",
            (profile_id,),
        ):
            line = EnrolledLine(r["idx"], r["start_s"], r["end_s"])
            known = calls.get(r["call_id"])
            lines = (*known.lines, line) if known else (line,)
            calls[r["call_id"]] = EnrolledCall(r["call_id"], r["start_local"], lines)
        return list(calls.values())

    def voice(self, profile_id: int, mean: Vector | None = None) -> Vector | None:
        """The person's centroid, whether or not the profile is usable yet, centered on mean."""
        return centroid(
            centered(
                [
                    (from_blob(r[0]), r[1])
                    for r in self._conn.execute(
                        "SELECT s.voiceprint, s.end_s - s.start_s FROM voice_samples v"
                        " JOIN segments s USING (call_id, idx) WHERE v.profile_id = ?",
                        (profile_id,),
                    )
                ],
                mean,
            )
        )

    def usable_voices(self, mean: Vector | None = None) -> dict[int, Vector]:
        """Centroids of every profile with enough enrolled speech for voice matching."""
        voices: dict[int, Vector] = {}
        for (profile_id,) in self._conn.execute("SELECT id FROM profiles ORDER BY id"):
            if (
                self.progress(profile_id).usable
                and (voice := self.voice(profile_id, mean)) is not None
            ):
                voices[profile_id] = voice
        return voices

    def _check_lines(self, call_id: int, wanted: Sequence[int]) -> None:
        if (
            self._conn.execute("SELECT 1 FROM transcripts WHERE call_id = ?", (call_id,)).fetchone()
            is None
        ):
            raise ProfileError(
                "call_not_transcribed", "Only a transcribed call's lines can be enrolled."
            )
        found = {
            r["idx"]: r["voiceprint"] is not None
            for r in self._conn.execute(
                "SELECT idx, voiceprint FROM segments WHERE call_id = ?", (call_id,)
            )
        }
        missing = [idx for idx in wanted if idx not in found]
        if missing:
            raise ProfileError("line_not_found", f"The call has no line {missing[0]}.")
        unprinted = [idx for idx in wanted if not found[idx]]
        if unprinted:
            raise ProfileError(
                "line_without_voiceprint",
                "Some ticked lines have no voiceprint: they are under a second long, or the call"
                " was transcribed before voiceprints were stored.",
            )


def call_prints(
    conn: sqlite3.Connection, call_id: int, mean: Vector | None = None
) -> list[tuple[Vector, float]]:
    """A call's stored line voiceprints with each line's length in seconds, centered on mean."""
    return centered(
        [
            (from_blob(r[0]), r[1])
            for r in conn.execute(
                "SELECT voiceprint, end_s - start_s FROM segments"
                " WHERE call_id = ? AND voiceprint IS NOT NULL ORDER BY idx",
                (call_id,),
            )
        ],
        mean,
    )
