import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from tests.clock import FakeClock
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.pipeline.audio import AudioError
from transcribr.pipeline.process import JobRunner, PipelineResult
from transcribr.pipeline.transcribe import Segment, Word
from transcribr.ravon.client import RavonClient
from transcribr.ravon.parse import Recording
from transcribr.store.calls import add_listed, is_listed, request_transcription
from transcribr.store.db import connect
from transcribr.store.migrate import migrate

CALL = 26541125


class StandInPipeline:
    """Returns a fixed two-line result; can be told to fail, and records call states seen."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.fail_next: list[BaseException] = []
        self.no_speech = False
        self.states_seen: list[str] = []
        self.runs = 0

    def run(self, audio: bytes) -> PipelineResult:
        self.runs += 1
        self.states_seen.append(
            self.conn.execute("SELECT state FROM calls WHERE id = ?", (CALL,)).fetchone()[0]
        )
        if self.fail_next:
            raise self.fail_next.pop(0)
        if self.no_speech:
            return PipelineResult("en", "small.en", ())
        segments = (
            Segment(0.0, 3.5, "this is Nolan", (Word(0.0, 1.0, "this"),)),
            Segment(4.0, 4.8, "a lift kit", (Word(4.0, 4.8, "a"),)),
        )
        return PipelineResult("en", "small.en", segments)


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        migrate(tmp_path / "t.db")
        self.conn = connect(tmp_path / "t.db")
        self.clock = FakeClock()
        self.fake = FakeRavon(calls=[FakeCall(CALL, "q", "2026-10-22 08:00:00", 1.0)])
        self.pipeline = StandInPipeline(self.conn)
        self.runner = self.make_runner()
        add_listed(
            self.conn,
            Recording(CALL, "2026-10-22 08:00:00", 1.0, "(405) 555-0100", "SW Counter Sales"),
            queue="q",
            zone="America/Chicago",
            now=self.clock.utcnow(),
            auto_queue=True,
        )

    def make_runner(self) -> JobRunner:
        return JobRunner(self.conn, self.make_client(), self.pipeline, now=self.clock.utcnow)

    def make_client(self) -> RavonClient:
        return RavonClient(
            "https://admin.ravon.net",
            self.fake.username,
            self.fake.password,
            transport=httpx.MockTransport(self.fake.handle),
            clock=self.clock,
            is_known_recording=is_listed(self.conn),
        )

    def state(self) -> tuple[str, str | None]:
        row = self.conn.execute(
            "SELECT state, failure_reason FROM calls WHERE id = ?", (CALL,)
        ).fetchone()
        return row[0], row[1]

    def attempts(self) -> int | None:
        row = self.conn.execute("SELECT attempts FROM jobs WHERE call_id = ?", (CALL,)).fetchone()
        return None if row is None else row[0]

    def later(self, minutes: float) -> None:
        self.clock.advance(minutes * 60)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_waiting_goes_to_processing_then_transcribed(rig: Rig) -> None:
    assert rig.state() == ("waiting", None)
    assert rig.runner.process_one(rig.conn)
    assert rig.pipeline.states_seen == ["processing"]
    assert rig.state() == ("transcribed", None)
    assert rig.attempts() is None  # job removed
    assert not rig.runner.process_one(rig.conn)  # nothing left


def test_the_transcript_is_stored_without_voice_data(rig: Rig) -> None:
    rig.runner.process_one(rig.conn)
    transcript = rig.conn.execute("SELECT * FROM transcripts").fetchone()
    assert (transcript["language"], transcript["model"], transcript["no_speech"]) == (
        "en",
        "small.en",
        0,
    )
    segments = rig.conn.execute("SELECT text, words FROM segments ORDER BY idx").fetchall()
    assert [s[0] for s in segments] == ["this is Nolan", "a lift kit"]
    assert segments[0][1] == '[[0.0, 1.0, "this"]]'
    hits = rig.conn.execute(
        "SELECT count(*) FROM segments_fts WHERE segments_fts MATCH '\"lift kit\"'"
    ).fetchone()[0]
    assert hits == 1


def test_no_speech_is_transcribed_with_a_marker(rig: Rig) -> None:
    rig.pipeline.no_speech = True
    rig.runner.process_one(rig.conn)
    assert rig.state() == ("transcribed", None)
    assert rig.conn.execute("SELECT no_speech FROM transcripts").fetchone()[0] == 1


def test_a_transient_failure_is_retried_and_succeeds(rig: Rig) -> None:
    rig.fake.truncate_audio = True
    rig.runner.process_one(rig.conn)
    assert rig.state()[0] == "waiting"
    assert rig.attempts() == 1
    assert not rig.runner.process_one(rig.conn)  # not due yet
    rig.fake.truncate_audio = False
    rig.later(1)
    assert rig.runner.process_one(rig.conn)
    assert rig.state() == ("transcribed", None)


def test_failure_after_three_retries_is_failed_with_a_reason(rig: Rig) -> None:
    rig.pipeline.fail_next = [AudioError("could not decode the recording: bad data")] * 4
    for minutes in (0, 1, 5, 30):
        rig.later(minutes)
        assert rig.runner.process_one(rig.conn)
    state, reason = rig.state()
    assert state == "failed"
    assert reason is not None and "could not decode" in reason
    assert rig.pipeline.runs == 4
    assert rig.attempts() is None


def test_retry_delays_grow(rig: Rig) -> None:
    rig.pipeline.fail_next = [AudioError("x")] * 3
    rig.runner.process_one(rig.conn)
    rig.later(0.9)
    assert not rig.runner.process_one(rig.conn)
    rig.later(0.2)
    assert rig.runner.process_one(rig.conn)  # second attempt after 1 min
    rig.later(4.9)
    assert not rig.runner.process_one(rig.conn)
    rig.later(0.2)
    assert rig.runner.process_one(rig.conn)  # third attempt after 5 min


def test_a_ravon_outage_does_not_use_up_retries(rig: Rig) -> None:
    rig.fake.reject_logins = True
    for _ in range(10):
        rig.later(2)
        rig.runner.process_one(rig.conn)
    assert rig.state() == ("waiting", None)
    assert rig.attempts() == 0
    assert rig.pipeline.runs == 0


def test_a_worker_killed_mid_call_starts_that_call_again(rig: Rig) -> None:
    rig.pipeline.fail_next = [KeyboardInterrupt()]  # the process dies mid-call
    with pytest.raises(KeyboardInterrupt):
        rig.runner.process_one(rig.conn)
    assert rig.state()[0] == "processing"

    restarted = rig.make_runner()
    restarted.recover()
    assert rig.state()[0] == "waiting"
    assert restarted.process_one(rig.conn)
    assert rig.state() == ("transcribed", None)


def test_manual_request_for_a_missed_call(rig: Rig) -> None:
    rig.conn.execute("DELETE FROM jobs")
    rig.conn.execute("UPDATE calls SET state = 'not_transcribed'")
    assert request_transcription(rig.conn, CALL, rig.clock.utcnow())
    assert rig.state()[0] == "waiting"
    assert rig.runner.process_one(rig.conn)
    assert rig.state() == ("transcribed", None)


@pytest.mark.parametrize("state", ["waiting", "processing", "transcribed"])
def test_manual_request_changes_nothing_in_other_states(rig: Rig, state: str) -> None:
    rig.conn.execute("UPDATE calls SET state = ?", (state,))
    before = rig.conn.execute("SELECT count(*), max(id) FROM jobs").fetchone()
    assert not request_transcription(rig.conn, CALL, rig.clock.utcnow())
    assert rig.conn.execute("SELECT count(*), max(id) FROM jobs").fetchone() == before
    assert rig.state()[0] == state


def test_retrying_a_failed_call_gets_a_fresh_count(rig: Rig) -> None:
    rig.pipeline.fail_next = [AudioError("x")] * 4
    for minutes in (0, 1, 5, 30):
        rig.later(minutes)
        rig.runner.process_one(rig.conn)
    assert rig.state()[0] == "failed"
    assert request_transcription(rig.conn, CALL, rig.clock.utcnow())
    assert rig.state() == ("waiting", None)
    assert rig.attempts() == 0


def test_a_call_from_an_earlier_run_can_still_be_downloaded(rig: Rig) -> None:
    # A fresh client has seen no search results; the database says the call is listed.
    assert rig.make_runner().process_one(rig.conn)
    assert rig.state() == ("transcribed", None)


def test_processing_leaves_no_audio_on_disk(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    rig.runner.process_one(rig.conn)
    assert [p for p in scratch.rglob("*") if p.is_file()] == []


def test_a_job_due_later_waits(rig: Rig) -> None:
    rig.conn.execute(
        "UPDATE jobs SET not_before = ?",
        ((rig.clock.utcnow() + timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),),
    )
    assert not rig.runner.process_one(rig.conn)


MODELS = Path(__file__).resolve().parents[2] / "models"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


@pytest.mark.model
@pytest.mark.skipif(
    not (MODELS / "faster-whisper-small.en" / "model.bin").exists(), reason="no models"
)
def test_end_to_end_with_the_real_models(rig: Rig) -> None:
    from transcribr.pipeline.process import ModelPipeline

    rig.fake.calls[0].audio = (FIXTURES / "two-voices.mp3").read_bytes()
    runner = JobRunner(rig.conn, rig.make_client(), ModelPipeline(MODELS), now=rig.clock.utcnow)
    assert runner.process_one()
    assert rig.state() == ("transcribed", None)
    lines = rig.conn.execute("SELECT start_s, end_s, text FROM segments ORDER BY idx").fetchall()
    assert "Nolan" in lines[0][2]
    columns = {r[1] for r in rig.conn.execute("PRAGMA table_info(segments)")}
    assert "voiceprint" not in columns  # no voice step runs
