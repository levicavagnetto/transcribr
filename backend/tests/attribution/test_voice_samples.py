import sqlite3

import numpy as np
import pytest

from tests.attribution.conftest import add_call, voice
from tests.clock import FakeClock
from transcribr.attribution.profiles import ProfileError, Profiles
from transcribr.attribution.voice import MIN_CALLS, MIN_SECONDS, VoiceSamples, centroid

NOLAN = voice(1.0, 0.1)
CUSTOMER = voice(0.1, 1.0)


@pytest.fixture
def samples(conn: sqlite3.Connection) -> VoiceSamples:
    return VoiceSamples(conn, now=FakeClock().utcnow)


@pytest.fixture
def nolan(conn: sqlite3.Connection) -> int:
    return Profiles(conn).create("Nolan", ["Nolan"]).id


def test_the_usability_rule_is_three_calls_and_thirty_seconds() -> None:
    assert (MIN_CALLS, MIN_SECONDS) == (3, 30.0)


def test_enroll_lines_from_a_call(
    conn: sqlite3.Connection, samples: VoiceSamples, nolan: int
) -> None:
    add_call(
        conn,
        1,
        [(0.0, 4.0, NOLAN), (4.5, 9.0, CUSTOMER), (9.5, 12.5, NOLAN), (13.0, 16.0, NOLAN)],
    )
    progress = samples.add(nolan, 1, [0, 2, 3])
    assert (progress.calls, progress.seconds) == (1, 10.0)
    [enrolled] = samples.enrolled(nolan)
    assert enrolled.call_id == 1
    assert [(line.idx, line.start_s, line.end_s) for line in enrolled.lines] == [
        (0, 0.0, 4.0),
        (2, 9.5, 12.5),
        (3, 13.0, 16.0),
    ]
    assert enrolled.seconds == 10.0
    assert samples.add(nolan, 1, [2, 2, 3]) == progress  # enrolling twice counts once


@pytest.mark.parametrize(
    ("call_id", "lines", "code"),
    [
        (1, [1], "line_without_voiceprint"),  # under a second
        (1, [0, 1], "line_without_voiceprint"),  # one bad line refuses the lot
        (2, [0], "line_without_voiceprint"),  # transcribed before voiceprints existed
        (1, [7], "line_not_found"),
        (3, [0], "call_not_transcribed"),
        (1, [], "no_lines"),
    ],
)
def test_lines_that_cannot_be_enrolled_are_refused(  # noqa: PLR0917 - fixtures, then the case
    conn: sqlite3.Connection,
    samples: VoiceSamples,
    nolan: int,
    call_id: int,
    lines: list[int],
    code: str,
) -> None:
    add_call(conn, 1, [(0.0, 4.0, NOLAN), (4.2, 4.8, None)])
    add_call(conn, 2, [(0.0, 6.0, None)])
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at) VALUES (3, 'q', 'x', 'x', 1, 'x', 'x', 't')"
    )
    with pytest.raises(ProfileError) as refused:
        samples.add(nolan, call_id, lines)
    assert refused.value.code == code
    assert samples.progress(nolan).calls == 0


def test_enrolling_for_an_unknown_person_is_refused(
    conn: sqlite3.Connection, samples: VoiceSamples
) -> None:
    add_call(conn, 1, [(0.0, 4.0, NOLAN)])
    with pytest.raises(ProfileError) as refused:
        samples.add(999, 1, [0])
    assert refused.value.code == "profile_not_found"


def test_the_centroid_is_the_duration_weighted_mean_at_unit_length() -> None:
    long, short = voice(1.0), voice(0.0, 1.0)
    result = centroid([(long, 9.0), (short, 1.0)])
    assert result is not None
    expected = np.array([0.9, 0.1] + [0.0] * 6) / np.linalg.norm([0.9, 0.1])
    assert np.allclose(result, expected, atol=1e-6)
    assert result.dtype == np.float32
    assert centroid([]) is None


def test_removing_a_calls_lines_rebuilds_the_voice_without_them(
    conn: sqlite3.Connection, samples: VoiceSamples, nolan: int
) -> None:
    add_call(conn, 1, [(0.0, 10.0, NOLAN)])
    add_call(conn, 2, [(0.0, 10.0, CUSTOMER)])  # a wrong enrollment
    samples.add(nolan, 1, [0])
    samples.add(nolan, 2, [0])
    mixed = samples.voice(nolan)
    assert mixed is not None and float(np.dot(mixed, NOLAN)) < 0.9

    progress = samples.remove_call(nolan, 2)

    assert (progress.calls, progress.seconds) == (1, 10.0)
    cleaned = samples.voice(nolan)
    assert cleaned is not None and float(np.dot(cleaned, NOLAN)) > 0.999
    assert [c.call_id for c in samples.enrolled(nolan)] == [1]


def test_a_retranscribed_call_takes_its_enrolled_lines_with_it(
    conn: sqlite3.Connection, samples: VoiceSamples, nolan: int
) -> None:
    add_call(conn, 1, [(0.0, 10.0, NOLAN)])
    samples.add(nolan, 1, [0])
    conn.execute("DELETE FROM transcripts WHERE call_id = 1")
    assert samples.voice(nolan) is None
    assert samples.progress(nolan).calls == 0


def enroll(
    conn: sqlite3.Connection, samples: VoiceSamples, profile: int, seconds: list[float]
) -> None:
    for n, length in enumerate(seconds):
        call_id = profile * 100 + n
        add_call(conn, call_id, [(0.0, length, NOLAN)])
        samples.add(profile, call_id, [0])


def test_not_enough_enrolled_speech(
    conn: sqlite3.Connection, samples: VoiceSamples, nolan: int
) -> None:
    enroll(conn, samples, nolan, [12.0, 8.0])
    progress = samples.progress(nolan)
    assert (progress.calls, progress.seconds, progress.usable) == (2, 20.0, False)
    assert (progress.calls_needed, progress.seconds_needed) == (1, 10.0)
    assert samples.usable_voices() == {}


@pytest.mark.parametrize(
    ("seconds", "usable"),
    [
        ([10.0, 10.0, 10.0], True),
        ([10.0, 10.0, 9.5], False),  # 3 calls but 29.5 s
        ([40.0, 10.0], False),  # 50 s but 2 calls
    ],
)
def test_voice_matching_starts_at_three_calls_and_thirty_seconds(
    conn: sqlite3.Connection, samples: VoiceSamples, nolan: int, seconds: list[float], usable: bool
) -> None:
    enroll(conn, samples, nolan, seconds)
    assert samples.progress(nolan).usable is usable
    assert (nolan in samples.usable_voices()) is usable
