from transcribr.attribution.names import NameHit
from transcribr.attribution.rules import Decision, decide

NOLAN, DANA = 1, 2
NAME = NameHit("Nolan", "Nolan.", 3.2)
DANA_NAME = NameHit("Dana", "Dana", 8.0)


def test_a_name_in_the_opening_is_a_maybe() -> None:
    assert decide({NOLAN: NAME}) == [Decision(NOLAN, "maybe", "name", NAME)]


def test_a_caller_asking_for_someone_is_still_only_a_maybe() -> None:
    # "Is Nolan there?" and "this is Nolan" look the same to the rule: a person decides.
    [decision] = decide({NOLAN: NameHit("Nolan", "Nolan?", 1.0)})
    assert decision.status == "maybe"


def test_transferred_call_with_two_staff() -> None:
    decisions = decide({NOLAN: NAME, DANA: DANA_NAME})
    assert [(d.profile_id, d.status) for d in decisions] == [(NOLAN, "maybe"), (DANA, "maybe")]


def test_no_name_leaves_the_call_unassigned() -> None:
    assert decide({NOLAN: None, DANA: None}) == []


def test_a_manual_decision_keeps_automatic_matching_off_that_person() -> None:
    decisions = decide({NOLAN: NAME, DANA: DANA_NAME}, manual={NOLAN})
    assert [d.profile_id for d in decisions] == [DANA]


def test_automatic_matching_never_makes_a_call_confident() -> None:
    assert {d.status for d in decide({NOLAN: NAME, DANA: DANA_NAME})} == {"maybe"}
