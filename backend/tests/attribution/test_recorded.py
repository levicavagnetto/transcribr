import sqlite3

from tests.attribution.conftest import add_call
from tests.clock import FakeClock
from transcribr.attribution.matching import load_context, rematch_all
from transcribr.attribution.profiles import Profiles
from transcribr.attribution.recorded import MIN_CALLS, RecordedMessage

GREETING = "Thank you for calling Tire Pros and Wheel Experts, your premier destination for tires"
HOLD = "Thank you for holding. If you're looking to schedule an appointment"
HOLD_CUT = "Thank you for holding. If you're looking"  # cut off where someone picked up
NOLAN = "Thanks for calling Tire Pros, this is Nolan. How can I help you?"


def message(calls: int = MIN_CALLS) -> RecordedMessage:
    return RecordedMessage.learn([[GREETING, HOLD, "and auto care."] for _ in range(calls)])


def test_lines_repeated_across_many_calls_are_recorded() -> None:
    recorded = message()
    assert recorded.is_recorded(GREETING)
    assert recorded.is_recorded(HOLD.upper())  # case and punctuation don't matter
    assert recorded.is_recorded("and auto care")  # a short fragment seen on every held call
    assert not recorded.is_recorded("I need four tires for my Silverado, how much are they?")
    assert not recorded.is_recorded("and that's it")


def test_lines_seen_on_too_few_calls_are_not_recorded() -> None:
    recorded = message(MIN_CALLS - 1)
    assert not recorded.is_recorded(GREETING)
    assert not recorded.is_recorded("and auto care")


def test_a_repeated_greeting_with_a_name_is_never_recorded() -> None:
    recorded = RecordedMessage.learn([[NOLAN] for _ in range(20)])
    assert recorded.is_recorded(NOLAN)  # it does repeat...
    assert not recorded.is_recorded(NOLAN, ["Nolan"])  # ...but a name keeps it


def add_held_call(conn: sqlite3.Connection, call_id: int, *, greeting_at: float) -> None:
    """The recorded greeting and hold message, then a staff greeting at `greeting_at`."""
    add_call(
        conn, call_id, [(4.0, 14.0), (40.0, 44.0), (44.0, 47.0), (greeting_at, greeting_at + 3)]
    )
    texts = [GREETING, HOLD_CUT, "you can schedule your appointments online", NOLAN]
    for idx, text in enumerate(texts):
        conn.execute(
            "UPDATE segments SET text = ? WHERE call_id = ? AND idx = ?", (text, call_id, idx)
        )


def test_greeting_after_the_hold_message(conn: sqlite3.Connection) -> None:
    nolan = Profiles(conn).create("Nolan", ["Nolan"]).id
    for call_id in range(1, MIN_CALLS + 1):
        add_held_call(conn, call_id, greeting_at=70.0)

    rematch_all(conn, FakeClock().utcnow())

    found = conn.execute(
        "SELECT count(*) FROM attributions WHERE profile_id = ? AND status = 'maybe'", (nolan,)
    ).fetchone()[0]
    assert found == MIN_CALLS


def test_a_late_name_after_ordinary_talk_still_does_not_count(conn: sqlite3.Connection) -> None:
    Profiles(conn).create("Nolan", ["Nolan"])
    add_call(conn, 1, [(0.0, 5.0), (40.0, 44.0)])
    conn.execute("UPDATE segments SET text = 'hi, I need a quote on tires' WHERE idx = 0")
    conn.execute("UPDATE segments SET text = 'you could ask Nolan about that' WHERE idx = 1")
    rematch_all(conn, FakeClock().utcnow())
    assert conn.execute("SELECT count(*) FROM attributions").fetchone()[0] == 0


def test_the_context_learns_from_the_stored_calls(conn: sqlite3.Connection) -> None:
    for call_id in range(1, MIN_CALLS + 1):
        add_held_call(conn, call_id, greeting_at=70.0)
    assert load_context(conn).recorded.is_recorded(GREETING)
