import sqlite3
from pathlib import Path

import pytest

from tests.attribution.conftest import add_call, voice
from tests.clock import FakeClock
from tests.pipeline.test_runner import CALL, Rig
from transcribr.attribution import matching
from transcribr.attribution.matching import Attributions, load_context, rematch_all
from transcribr.attribution.profiles import ProfileError, Profiles
from transcribr.attribution.queue import REMATCH, request_rematch
from transcribr.attribution.voice import VoiceSamples
from transcribr.pipeline.process import JobRunner, PipelineResult
from transcribr.pipeline.transcribe import Word
from transcribr.pipeline.voiceprint import Line
from transcribr.settings import VOICE_HIGH, VOICE_LOW, Settings

NOLAN_VOICE = voice(1.0, 0.1)
CUSTOMER = voice(0.1, 1.0)
DANA_VOICE = voice(0.0, 0.1, 1.0)


def rows(conn: sqlite3.Connection, call_id: int) -> list[tuple[object, ...]]:
    return [
        tuple(r)
        for r in conn.execute(
            "SELECT profile_id, status, source, method, name_heard, voice_score"
            " FROM attributions WHERE call_id = ? ORDER BY profile_id",
            (call_id,),
        )
    ]


def rematch_jobs(conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    return [
        tuple(r)
        for r in conn.execute("SELECT claimed_at FROM jobs WHERE type = ? ORDER BY id", (REMATCH,))
    ]


def add_named_call(conn: sqlite3.Connection, call_id: int, opening: str) -> None:
    """A call whose only line is `opening`, without word times or voiceprints."""
    add_call(conn, call_id, [(0.0, 3.0, None)])
    conn.execute("UPDATE segments SET text = ? WHERE call_id = ?", (opening, call_id))


@pytest.fixture
def people(conn: sqlite3.Connection) -> tuple[int, int]:
    profiles = Profiles(conn)
    return profiles.create("Nolan", ["Nolan"]).id, profiles.create("Dana", ["Dana"]).id


# --- manual decisions (4.4) ---------------------------------------------------------------


def test_claim_a_missed_call(conn: sqlite3.Connection, people: tuple[int, int]) -> None:
    nolan, _ = people
    add_named_call(conn, 1, "hello who is this")
    Attributions(conn).claim(1, nolan)
    assert rows(conn, 1) == [(nolan, "confident", "manual", "manual", None, None)]


def test_reject_a_wrong_match_and_it_stays_rejected(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, _ = people
    add_named_call(conn, 1, "is Nolan there")
    rematch_all(conn, FakeClock().utcnow())
    assert rows(conn, 1)[0][1:4] == ("confident", "auto", "name")

    Attributions(conn).reject(1, nolan)
    rematch_all(conn, FakeClock().utcnow())

    assert rows(conn, 1)[0][1:4] == ("rejected", "manual", "manual")


def test_confirm_a_maybe(conn: sqlite3.Connection, people: tuple[int, int]) -> None:
    nolan, dana = people
    add_named_call(conn, 1, "hello")
    conn.execute(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, voice_score,"
        " updated_at) VALUES (1, ?, 'maybe', 'auto', 'voice', 0.6, 't')",
        (nolan,),
    )
    Attributions(conn).confirm(1, nolan)
    assert rows(conn, 1) == [(nolan, "confident", "manual", "manual", None, 0.6)]
    with pytest.raises(ProfileError) as refused:
        Attributions(conn).confirm(1, nolan)  # already Confident
    assert refused.value.code == "not_maybe"
    with pytest.raises(ProfileError):
        Attributions(conn).confirm(1, dana)  # no attribution at all


def test_claiming_keeps_the_evidence_already_found(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, _ = people
    add_named_call(conn, 1, "this is Nolan")
    rematch_all(conn, FakeClock().utcnow())
    Attributions(conn).claim(1, nolan)
    assert rows(conn, 1) == [(nolan, "confident", "manual", "manual", "Nolan", None)]


def test_manual_decisions_need_a_real_call_and_person(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, _ = people
    add_named_call(conn, 1, "hello")
    for call_id, profile_id, code in (
        (999, nolan, "call_not_found"),
        (1, 999, "profile_not_found"),
    ):
        with pytest.raises(ProfileError) as refused:
            Attributions(conn).claim(call_id, profile_id)
        assert refused.value.code == code


def test_rematch_never_touches_manual_rows(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, dana = people
    add_named_call(conn, 1, "this is Dana")
    Attributions(conn).claim(1, nolan)
    rematch_all(conn, FakeClock().utcnow())
    rematch_all(conn, FakeClock().utcnow())
    assert [r[:3] for r in rows(conn, 1)] == [
        (nolan, "confident", "manual"),
        (dana, "confident", "auto"),
    ]


# --- matching from stored data -------------------------------------------------------------


def enroll_nolan(conn: sqlite3.Connection, nolan: int) -> None:
    for call_id in (901, 902, 903):
        add_call(conn, call_id, [(0.0, 12.0, NOLAN_VOICE)])
        VoiceSamples(conn).add(nolan, call_id, [0])


def test_voice_and_name_together(conn: sqlite3.Connection, people: tuple[int, int]) -> None:
    nolan, dana = people
    enroll_nolan(conn, nolan)
    add_call(conn, 1, [(0.0, 6.0, NOLAN_VOICE), (6.5, 14.0, CUSTOMER)])  # outbound, no name
    add_call(conn, 2, [(0.0, 3.0, None), (3.5, 9.0, CUSTOMER)])  # caller asks for Nolan
    conn.execute("UPDATE segments SET text = 'is Nolan there' WHERE call_id = 2 AND idx = 0")
    add_call(conn, 3, [(0.0, 9.0, CUSTOMER)])  # nobody we know

    rematch_all(conn, FakeClock().utcnow())

    assert rows(conn, 1) == [(nolan, "confident", "auto", "voice", None, pytest.approx(1.0))]
    [(profile, status, _, method, heard, score)] = rows(conn, 2)
    assert (profile, status, method, heard) == (nolan, "maybe", "name", "Nolan")
    assert isinstance(score, float) and score < 0.5
    assert rows(conn, 3) == []
    assert dana not in {r[0] for r in rows(conn, 1)}


def test_thresholds_come_from_the_settings(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, _ = people
    enroll_nolan(conn, nolan)
    add_call(conn, 1, [(0.0, 9.0, voice(1.0, 0.6))])  # sounds a bit like Nolan
    score = float(voice(1.0, 0.6) @ NOLAN_VOICE)

    Settings(conn).set_many({VOICE_LOW.key: score - 0.1, VOICE_HIGH.key: score + 0.05})
    rematch_all(conn, FakeClock().utcnow())
    assert rows(conn, 1)[0][1:4] == ("maybe", "auto", "voice")

    Settings(conn).set(VOICE_HIGH, score - 0.01)
    rematch_all(conn, FakeClock().utcnow())
    assert rows(conn, 1)[0][1:4] == ("confident", "auto", "voice")
    assert load_context(conn).high == pytest.approx(score - 0.01)


# --- rematch jobs (4.5) --------------------------------------------------------------------


def test_profile_and_sample_changes_queue_one_rematch(
    conn: sqlite3.Connection, people: tuple[int, int]
) -> None:
    nolan, dana = people  # creating two people queued one job, not two
    assert rematch_jobs(conn) == [(None,)]
    Profiles(conn).update(dana, "Dana", ["Dana", "Danna"])
    add_call(conn, 1, [(0.0, 5.0, NOLAN_VOICE)])
    VoiceSamples(conn).add(nolan, 1, [0])
    VoiceSamples(conn).remove_call(nolan, 1)
    Profiles(conn).delete(dana)
    assert rematch_jobs(conn) == [(None,)]

    conn.execute("UPDATE jobs SET claimed_at = 'now' WHERE type = ?", (REMATCH,))
    request_rematch(conn, FakeClock().utcnow())  # a running rematch read the old profiles
    assert rematch_jobs(conn) == [("now",), (None,)]


class NoModel:
    """A pipeline that must never be asked to run."""

    runs = 0

    def run(self, audio: bytes) -> PipelineResult:
        self.runs += 1
        raise AssertionError("a rematch must not load or run a model")


def test_a_rematch_over_100_calls_uses_stored_data_only(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    conn = rig.conn
    conn.execute("DELETE FROM jobs")  # the rig's own call isn't transcribed
    nolan = Profiles(conn).create("Nolan", ["Nolan"]).id
    enroll_nolan(conn, nolan)
    for n in range(100):
        call_id = 1000 + n
        lines = [(0.0, 6.0, NOLAN_VOICE if n % 2 == 0 else CUSTOMER), (6.5, 12.0, CUSTOMER)]
        add_call(conn, call_id, lines)
    Attributions(conn, now=rig.clock.utcnow).reject(1000, nolan)
    Attributions(conn, now=rig.clock.utcnow).claim(1001, nolan)
    manual_before = conn.execute(
        "SELECT * FROM attributions WHERE source = 'manual' ORDER BY call_id"
    ).fetchall()

    pipeline = NoModel()
    runner = JobRunner(conn, rig.make_client(), pipeline, now=rig.clock.utcnow)
    assert runner.process_one()

    assert rematch_jobs(conn) == []
    assert rig.fake.requests == []
    assert pipeline.runs == 0
    manual_after = conn.execute(
        "SELECT * FROM attributions WHERE source = 'manual' ORDER BY call_id"
    ).fetchall()
    assert [tuple(r) for r in manual_after] == [tuple(r) for r in manual_before]
    by_voice = conn.execute(
        "SELECT count(*) FROM attributions WHERE source = 'auto' AND method = 'voice'"
        " AND call_id BETWEEN 1000 AND 1099"
    ).fetchone()[0]
    assert by_voice == 49  # the even calls, less the rejected one


def test_a_failed_rematch_is_retried_later(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path)
    rig.conn.execute("DELETE FROM jobs")
    Profiles(rig.conn).create("Nolan", ["Nolan"])

    def broken(*_args: object) -> int:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("transcribr.pipeline.process.rematch_all", broken)
    runner = JobRunner(rig.conn, rig.make_client(), NoModel(), now=rig.clock.utcnow)
    assert runner.process_one()
    job = rig.conn.execute("SELECT * FROM jobs WHERE type = ?", (REMATCH,)).fetchone()
    assert (job["claimed_at"], job["attempts"]) == (None, 1)
    assert "disk on fire" in job["last_error"]
    assert not runner.process_one()  # not due yet
    rig.later(1.5)
    monkeypatch.setattr("transcribr.pipeline.process.rematch_all", matching.rematch_all)
    assert runner.process_one()
    assert rematch_jobs(rig.conn) == []


class Greeting:
    """Transcribes every call as Nolan answering, with a voiceprint that sounds like him."""

    def run(self, audio: bytes) -> PipelineResult:
        words = tuple(
            Word(0.4 * n, 0.4 * n + 0.3, w)
            for n, w in enumerate(["Tire", "Pros,", "this", "is", "Nolan."])
        )
        line = Line(0.0, 6.0, "Tire Pros, this is Nolan.", words, NOLAN_VOICE)
        return PipelineResult("en", "small.en", (line,))


def test_a_new_call_is_attributed_when_it_is_transcribed(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    nolan = Profiles(rig.conn).create("Nolan", ["Nolan"]).id
    rig.conn.execute("DELETE FROM jobs WHERE type = ?", (REMATCH,))
    runner = JobRunner(rig.conn, rig.make_client(), Greeting(), now=rig.clock.utcnow)

    assert runner.process_one()

    assert rig.state() == ("transcribed", None)
    [(profile, status, source, method, heard, score)] = rows(rig.conn, CALL)
    assert (profile, status, source, method, heard, score) == (
        nolan,
        "confident",
        "auto",
        "name",  # no usable voice profile yet
        "Nolan.",
        None,
    )
