import pytest

from transcribr.attribution.names import NameHit
from transcribr.attribution.rules import Decision, Evidence, decide

LOW, HIGH = 0.5, 0.7
NOLAN, DANA = 1, 2
NAME = NameHit("Nolan", "Nolan.", 3.2)

STRONG, WEAK, NONE = 0.8, 0.6, 0.2


def ev(*, name: bool = False, usable: bool = True, presence: float | None = None) -> Evidence:
    return Evidence(NAME if name else None, usable, presence if usable else None)


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        # Strong voice: Confident.
        (ev(presence=STRONG), ("confident", "voice", STRONG)),  # outbound call without a name
        (ev(presence=HIGH), ("confident", "voice", HIGH)),  # at the threshold counts
        # Name with strong or weak voice: Confident.
        (ev(name=True, presence=STRONG), ("confident", "name+voice", STRONG)),
        (ev(name=True, presence=WEAK), ("confident", "name+voice", WEAK)),
        # Name with no voice profile yet: Confident.
        (ev(name=True, usable=False), ("confident", "name", None)),
        # Name on a call too short to tell by voice: Confident.
        (ev(name=True, presence=None), ("confident", "name", None)),
        # Name where the voice profile has no voice match, even weak: Maybe.
        (ev(name=True, presence=NONE), ("maybe", "name", NONE)),  # caller asks for someone
        # Weak voice alone: Maybe.
        (ev(presence=WEAK), ("maybe", "voice", WEAK)),
        (ev(presence=LOW), ("maybe", "voice", LOW)),
        # No evidence.
        (ev(presence=NONE), None),
        (ev(presence=None), None),
        (ev(usable=False), None),
    ],
)
def test_automatic_attribution_rules(
    evidence: Evidence, expected: tuple[str, str, float | None] | None
) -> None:
    decisions = decide({NOLAN: evidence}, low=LOW, high=HIGH)
    if expected is None:
        assert decisions == []
        return
    status, method, score = expected
    assert decisions == [Decision(NOLAN, status, method, evidence.name, score)]


def test_transferred_call_with_two_staff() -> None:
    decisions = decide({NOLAN: ev(presence=STRONG), DANA: ev(presence=0.75)}, low=LOW, high=HIGH)
    assert [(d.profile_id, d.status) for d in decisions] == [
        (NOLAN, "confident"),
        (DANA, "confident"),
    ]


def test_no_evidence_leaves_the_call_unassigned() -> None:
    assert decide({NOLAN: ev(presence=NONE), DANA: ev(usable=False)}, low=LOW, high=HIGH) == []


def test_a_manual_decision_keeps_automatic_matching_off_that_person() -> None:
    decisions = decide(
        {NOLAN: ev(name=True, presence=STRONG), DANA: ev(presence=STRONG)},
        low=LOW,
        high=HIGH,
        manual={NOLAN},
    )
    assert [d.profile_id for d in decisions] == [DANA]


def test_an_unusable_profiles_voice_score_is_not_reported() -> None:
    [decision] = decide({NOLAN: Evidence(NAME, False, 0.9)}, low=LOW, high=HIGH)
    assert (decision.method, decision.voice_score) == ("name", None)
