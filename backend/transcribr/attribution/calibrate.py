"""`transcribr calibrate`: voice scores of chosen calls against one profile (design D9).

Reads stored line voiceprints only: no Ravon requests, no models, no audio. The report holds
numbers and call IDs, never transcript text.
"""

import csv
import io
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from transcribr.attribution.profiles import ProfileError, Profiles
from transcribr.attribution.voice import (
    VoiceSamples,
    call_prints,
    instance_mean,
    line_scores,
    presence_score,
)

PRESENCE_MINIMUMS = (2.0, 4.0, 6.0, 8.0)


@dataclass(frozen=True)
class CalibrationRow:
    call_id: int
    voiced_seconds: float
    best_line_score: float | None
    presence: tuple[float | None, ...]  # one per PRESENCE_MINIMUMS
    enrolled: bool  # lines from this call are in the voice profile, so it isn't a fair test


def calibrate(
    conn: sqlite3.Connection, profile_id: int, call_ids: Sequence[int]
) -> list[CalibrationRow]:
    Profiles(conn).get(profile_id)
    mean = instance_mean(conn)
    voice = VoiceSamples(conn).voice(profile_id, mean)
    if voice is None:
        raise ProfileError("no_voice", "Enroll some of this person's lines first.")
    enrolled = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT call_id FROM voice_samples WHERE profile_id = ?", (profile_id,)
        )
    }
    rows: list[CalibrationRow] = []
    for call_id in call_ids:
        if (
            conn.execute("SELECT 1 FROM transcripts WHERE call_id = ?", (call_id,)).fetchone()
            is None
        ):
            raise ProfileError("call_not_transcribed", f"Call {call_id} has no transcript.")
        scores = line_scores(call_prints(conn, call_id, mean), voice)
        rows.append(
            CalibrationRow(
                call_id,
                sum(seconds for seconds, _ in scores),
                max((score for _, score in scores), default=None),
                tuple(presence_score(scores, m) for m in PRESENCE_MINIMUMS),
                call_id in enrolled,
            )
        )
    return rows


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def report_csv(profile_id: int, rows: Sequence[CalibrationRow]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        [
            "profile_id",
            "call_id",
            "voiced_seconds",
            "best_line_score",
            *(f"presence_at_{m:g}s" for m in PRESENCE_MINIMUMS),
            "enrolled",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                profile_id,
                row.call_id,
                f"{row.voiced_seconds:.1f}",
                _number(row.best_line_score),
                *(_number(p) for p in row.presence),
                "yes" if row.enrolled else "no",
            ]
        )
    return out.getvalue()


def write_report(
    conn: sqlite3.Connection,
    profile_id: int,
    call_ids: Sequence[int],
    reports_dir: Path,
    now: datetime,
) -> tuple[Path, str]:
    """Score the calls and write the CSV report; returns its path and text."""
    text = report_csv(profile_id, calibrate(conn, profile_id, call_ids))
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"calibration-profile{profile_id}-{now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    path.write_text(text, encoding="utf-8", newline="")
    return path, text
