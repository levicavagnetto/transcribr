"""Turning queued calls into stored transcripts: the job runner (design D3) and the pipeline.

The runner also does rematch jobs: they read stored data only, so they need no audio or model.
"""

import json
import logging
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from transcribr.attribution.matching import attribute_call, load_context, rematch_all
from transcribr.attribution.queue import REMATCH
from transcribr.pipeline.audio import AudioError, decode
from transcribr.pipeline.transcribe import Segment, Transcriber
from transcribr.ravon.client import (
    LoginRejected,
    NoCredentials,
    RavonClient,
    RavonUnavailable,
)
from transcribr.store.calls import TRANSCRIBE
from transcribr.store.db import transaction
from transcribr.timeutil import to_iso, utcnow

log = logging.getLogger(__name__)

RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))
RAVON_WAIT = timedelta(minutes=1)
MAX_REASON = 500


@dataclass(frozen=True)
class PipelineResult:
    language: str
    model: str
    segments: tuple[Segment, ...]

    @property
    def no_speech(self) -> bool:
        return not any(s.text.strip() for s in self.segments)


class Pipeline(Protocol):
    def run(self, audio: bytes) -> PipelineResult: ...


class ModelPipeline:
    """Decode, then transcribe. The model loads on first use and stays loaded."""

    def __init__(
        self,
        models_dir: Path,
        *,
        hotwords: Callable[[], Sequence[str]] = tuple,
        transcriber: Transcriber | None = None,
    ) -> None:
        self._models_dir = models_dir
        self._hotwords = hotwords  # read before each call, so profile changes apply at once
        self._transcriber = transcriber

    def run(self, audio: bytes) -> PipelineResult:
        samples = decode(audio)
        if self._transcriber is None:
            self._transcriber = Transcriber(self._models_dir)
        transcript = self._transcriber.transcribe(samples, hotwords=self._hotwords())
        segments = () if transcript.no_speech else tuple(transcript.segments)
        return PipelineResult(transcript.language, transcript.model, segments)


@dataclass(frozen=True)
class _Claimed:
    job_id: int
    call_id: int
    attempts: int


class JobRunner:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: RavonClient,
        pipeline: Pipeline,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._conn = conn
        self._client = client
        self._pipeline = pipeline
        self._now = now

    def recover(self) -> None:
        """On start: a call left Processing by a crash goes back to Waiting."""
        with transaction(self._conn):
            self._conn.execute("UPDATE jobs SET claimed_at = NULL WHERE claimed_at IS NOT NULL")
            count = self._conn.execute(
                "UPDATE calls SET state = 'waiting' WHERE state = 'processing'"
            ).rowcount
        if count:
            log.warning("%d call(s) were mid-processing when the worker stopped; requeued", count)

    def process_one(self, _conn: sqlite3.Connection | None = None) -> bool:
        """Process the next due job, if any. Returns whether one was attempted."""
        if self._rematch_one():
            return True
        claimed = self._claim()
        if claimed is None:
            return False
        try:
            audio = self._client.download(claimed.call_id)
            result = self._pipeline.run(audio)
        except (RavonUnavailable, LoginRejected, NoCredentials) as error:
            self._wait_for_ravon(claimed, error)
        except Exception as error:
            self._attempt_failed(claimed, error)
        else:
            self._store(claimed, result)
        return True

    def _rematch_one(self) -> bool:
        now = to_iso(self._now())
        with transaction(self._conn):
            row = self._conn.execute(
                "SELECT id, attempts FROM jobs WHERE type = ? AND claimed_at IS NULL"
                " AND (not_before IS NULL OR not_before <= ?) ORDER BY id LIMIT 1",
                (REMATCH, now),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("UPDATE jobs SET claimed_at = ? WHERE id = ?", (now, row["id"]))
        try:
            count = rematch_all(self._conn, self._now())
        except Exception as error:
            attempts: int = row["attempts"] + 1
            delay = RETRY_DELAYS[min(attempts, len(RETRY_DELAYS)) - 1]
            log.exception("rematch failed (attempt %d), will retry", attempts)
            self._conn.execute(
                "UPDATE jobs SET claimed_at = NULL, attempts = ?, not_before = ?, last_error = ?"
                " WHERE id = ?",
                (attempts, to_iso(self._now() + delay), _reason(error), row["id"]),
            )
            return True
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (row["id"],))
        log.info("rematched %d call(s)", count)
        return True

    def _claim(self) -> _Claimed | None:
        now = to_iso(self._now())
        with transaction(self._conn):
            row = self._conn.execute(
                "SELECT id, call_id, attempts FROM jobs WHERE type = ? AND claimed_at IS NULL"
                " AND (not_before IS NULL OR not_before <= ?) ORDER BY id LIMIT 1",
                (TRANSCRIBE, now),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute("UPDATE jobs SET claimed_at = ? WHERE id = ?", (now, row["id"]))
            self._conn.execute(
                "UPDATE calls SET state = 'processing' WHERE id = ?", (row["call_id"],)
            )
        return _Claimed(row["id"], row["call_id"], row["attempts"])

    def _release(self, claimed: _Claimed, *, attempts: int, delay: timedelta, error: str) -> None:
        with transaction(self._conn):
            self._conn.execute(
                "UPDATE jobs SET claimed_at = NULL, attempts = ?, not_before = ?, last_error = ?"
                " WHERE id = ?",
                (attempts, to_iso(self._now() + delay), error[:MAX_REASON], claimed.job_id),
            )
            self._conn.execute(
                "UPDATE calls SET state = 'waiting' WHERE id = ?", (claimed.call_id,)
            )

    def _wait_for_ravon(self, claimed: _Claimed, error: Exception) -> None:
        log.info("call %d waits for Ravon: %s", claimed.call_id, error)
        self._release(claimed, attempts=claimed.attempts, delay=RAVON_WAIT, error=str(error))

    def _attempt_failed(self, claimed: _Claimed, error: Exception) -> None:
        attempts = claimed.attempts + 1
        reason = _reason(error)
        if attempts <= len(RETRY_DELAYS):
            log.warning(
                "call %d failed (attempt %d), will retry: %s", claimed.call_id, attempts, reason
            )
            self._release(
                claimed, attempts=attempts, delay=RETRY_DELAYS[attempts - 1], error=reason
            )
            return
        log.error("call %d failed after %d attempts: %s", claimed.call_id, attempts, reason)
        with transaction(self._conn):
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (claimed.job_id,))
            self._conn.execute(
                "UPDATE calls SET state = 'failed', failure_reason = ?, failed_at = ? WHERE id = ?",
                (reason, to_iso(self._now()), claimed.call_id),
            )

    def _store(self, claimed: _Claimed, result: PipelineResult) -> None:
        call_id = claimed.call_id
        with transaction(self._conn):
            self._conn.execute("DELETE FROM transcripts WHERE call_id = ?", (call_id,))
            self._conn.execute(
                "INSERT INTO transcripts (call_id, language, model, transcribed_at, no_speech)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    call_id,
                    result.language,
                    result.model,
                    to_iso(self._now()),
                    int(result.no_speech),
                ),
            )
            self._conn.executemany(
                "INSERT INTO segments (call_id, idx, start_s, end_s, text, words)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        call_id,
                        index,
                        s.start,
                        s.end,
                        s.text,
                        json.dumps([[w.start, w.end, w.text] for w in s.words]),
                    )
                    for index, s in enumerate(result.segments)
                ],
            )
            attribute_call(self._conn, call_id, load_context(self._conn), self._now())
            self._conn.execute(
                "UPDATE calls SET state = 'transcribed', failure_reason = NULL WHERE id = ?",
                (call_id,),
            )
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (claimed.job_id,))
        log.info("call %d transcribed (%d lines)", call_id, len(result.segments))


def _reason(error: Exception) -> str:
    if isinstance(error, AudioError):
        return str(error)
    return f"{type(error).__name__}: {error}"[:MAX_REASON]
