import pytest

from tests.attribution.conftest import voice
from transcribr.attribution.voice import MIN_PRESENCE_SECONDS, band, line_scores, presence_score

LOW, HIGH = 0.5, 0.7


def test_the_calibrated_minimum_presence_is_two_seconds() -> None:
    assert MIN_PRESENCE_SECONDS == 2.0


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        # (seconds, score) per line -> presence score
        ([(5.0, 0.8)], 0.8),  # one long matching line is enough
        ([(2.0, 0.9), (2.0, 0.75), (6.0, 0.1)], 0.75),  # the top 4 s reach 0.75
        ([(1.5, 0.95), (3.0, 0.2), (4.0, 0.1)], 0.2),  # too little matching speech
        ([(1.0, 0.9), (1.0, 0.8), (1.0, 0.7), (1.0, 0.6)], 0.6),  # exactly 4 s
        ([(2.0, 0.1), (2.0, 0.9)], 0.1),  # order of lines doesn't matter
        ([(1.5, 0.9), (1.5, 0.9)], None),  # 3 s of voiceprinted speech: no score
        ([], None),
    ],
)
def test_presence_score(lines: list[tuple[float, float]], expected: float | None) -> None:
    assert presence_score(lines, 4.0) == expected  # the rule at a 4 s minimum


def test_the_minimum_presence_can_be_changed() -> None:
    lines = [(2.0, 0.9), (2.0, 0.6), (4.0, 0.3)]
    assert [presence_score(lines, m) for m in (2.0, 4.0, 6.0, 8.0, 9.0)] == [
        0.9,
        0.6,
        0.3,
        0.3,
        None,
    ]


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.9, "strong"), (0.7, "strong"), (0.69, "weak"), (0.5, "weak"), (0.49, None), (None, None)],
)
def test_bands(score: float | None, expected: str | None) -> None:
    assert band(score, LOW, HIGH) == expected


def test_too_little_matching_speech_is_not_a_strong_match() -> None:
    nolan = voice(1.0)
    prints = [(voice(1.0, 0.05), 1.5), (voice(0.0, 1.0), 5.0), (voice(0.1, 0.0, 1.0), 6.0)]
    scores = line_scores(prints, nolan)
    assert max(score for _, score in scores) >= HIGH  # one short line sounds like Nolan
    assert band(presence_score(scores), LOW, HIGH) is None


def test_line_scores_are_cosine_similarity() -> None:
    same, other = voice(1.0), voice(0.0, 1.0)
    assert line_scores([(same, 2.0), (other, 3.0)], same) == [
        (2.0, pytest.approx(1.0)),
        (3.0, pytest.approx(0.0)),
    ]
