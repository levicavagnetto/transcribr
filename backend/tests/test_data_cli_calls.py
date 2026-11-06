"""The `transcribr calls ...` commands (add-data-cli group 2)."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from transcribr.attribution.matching import Attributions, rematch_all
from transcribr.attribution.profiles import Profiles
from transcribr.cli import main
from transcribr.ravon.parse import Recording
from transcribr.settings import TIME_ZONE, Settings
from transcribr.store.calls import add_listed
from transcribr.store.db import connect, digits_only
from transcribr.store.migrate import migrate
from transcribr.timeutil import utcnow


@pytest.fixture
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sqlite3.Connection]:
    folder = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(folder))
    migrate(folder / "transcribr.db")
    conn = connect(folder / "transcribr.db")
    yield conn
    conn.close()


def _listed(conn: sqlite3.Connection) -> int:
    """A call that is listed but Not transcribed."""
    add_listed(
        conn,
        Recording(90000001, "2026-11-05 09:00:00", 60.0, "(580) 555-0119", "SW Counter Sales"),
        queue="q",
        zone="America/Chicago",
        now=datetime(2026, 11, 5, 15, tzinfo=UTC),
        auto_queue=False,
    )
    return int(conn.execute("SELECT max(id) FROM calls").fetchone()[0])


def _transcribed(
    conn: sqlite3.Connection,
    call_id: int,
    lines: list[str],
    *,
    day: str,
    number: str = "(405) 555-0142",
) -> None:
    """A Transcribed call at 08:00 Chicago time on `day`, one line every 5 s."""
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " caller_digits, answered_by, listed_at, state)"
        " VALUES (?, 'q', ?, ?, 2, ?, ?, 'y', 't', 'transcribed')",
        (call_id, f"{day} 08:00:00", f"{day}T14:00:00Z", number, digits_only(number)),
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (?, 'en', 'small.en', 't')",
        (call_id,),
    )
    conn.executemany(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text) VALUES (?, ?, ?, ?, ?)",
        [(call_id, i, 5.0 * i, 5.0 * i + 4, text) for i, text in enumerate(lines)],
    )
    conn.commit()


@pytest.fixture
def shop(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Three calls: a Maybe for Nolan by name, one confirmed for Sam, and one nobody is on."""
    Settings(conn).set(TIME_ZONE, "America/Chicago")
    nolan_lines = ["Thanks for calling, this is Nolan.", "I need brake pads."]
    _transcribed(conn, 1, nolan_lines, day="2026-11-03")
    _transcribed(conn, 2, ["Hi, this is Sam.", "Your tires are ready."], day="2026-11-04")
    _transcribed(conn, 3, ["Hello?", "Wrong number."], day="2026-11-05", number="(580) 555-0119")
    Profiles(conn).create("Nolan", ["Nolan"])
    sam = Profiles(conn).create("Sam", ["Sam"]).id
    rematch_all(conn, utcnow())
    Attributions(conn).confirm(2, sam)
    return conn


def _json(argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    assert main([*argv, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def _ids(argv: list[str], capsys: pytest.CaptureFixture[str]) -> list[int]:
    return [c["id"] for c in _json(argv, capsys)["calls"]]


# --- calls list (task 2.1) -------------------------------------------------------


@pytest.mark.usefixtures("shop")
def test_list_is_newest_first_with_people(capsys: pytest.CaptureFixture[str]) -> None:
    calls = _json(["calls", "list"], capsys)["calls"]
    assert [c["id"] for c in calls] == [3, 2, 1]
    assert calls[2]["attributions"][0]["display_name"] == "Nolan"
    assert calls[2]["attributions"][0]["status"] == "maybe"
    assert "passage" not in calls[0]


@pytest.mark.usefixtures("shop")
def test_list_as_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("#3  2026-11-05 08:00:00  (580) 555-0119  2 min  Transcribed")
    assert lines[1].endswith("people: Sam (Confident, set by hand)")
    assert lines[2].endswith("people: Nolan (Maybe, by name)")


@pytest.mark.usefixtures("shop")
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (["--person", "nolan"], [1]),
        (["--person", "Sam"], [2]),
        (["--maybe"], [1]),
        (["--person", "Sam", "--maybe"], []),
        (["--unassigned"], [3]),
        (["--from", "2026-11-04"], [3, 2]),
        (["--to", "2026-11-04"], [2, 1]),
        (["--from", "2026-11-04", "--to", "2026-11-04"], [2]),
        (["--number", "555-0119"], [3]),
        (["--state", "failed"], []),
        (["--limit", "2"], [3, 2]),
        (["--limit", "0"], [3, 2, 1]),
    ],
)
def test_list_filters(
    filters: list[str], expected: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _ids(["calls", "list", *filters], capsys) == expected


@pytest.mark.usefixtures("shop")
def test_no_matches_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "list", "--state", "failed"]) == 0
    assert capsys.readouterr().out == "No calls match.\n"


@pytest.mark.usefixtures("shop")
def test_unassigned_with_a_person_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "list", "--unassigned", "--person", "Sam", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_filter"


@pytest.mark.usefixtures("shop")
def test_an_unknown_person_filter_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "list", "--person", "Bob"]) == 1
    assert "No person is named Bob." in capsys.readouterr().err


# --- calls search (task 2.2) -----------------------------------------------------


@pytest.mark.usefixtures("shop")
def test_search_finds_the_phrase_and_its_line(capsys: pytest.CaptureFixture[str]) -> None:
    calls = _json(["calls", "search", "brake pads"], capsys)["calls"]
    assert [c["id"] for c in calls] == [1]
    assert calls[0]["match"] == {"at_s": 5.0, "text": "I need brake pads."}
    assert main(["calls", "search", "brake pads"]) == 0
    assert "    [0:05] I need brake pads." in capsys.readouterr().out


@pytest.mark.usefixtures("shop")
def test_search_takes_the_same_filters(capsys: pytest.CaptureFixture[str]) -> None:
    assert _ids(["calls", "search", "this is"], capsys) == [2, 1]
    assert _ids(["calls", "search", "this is", "--person", "Sam"], capsys) == [2]


@pytest.mark.usefixtures("shop")
def test_search_without_words_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "search", "?!", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_search"


# --- calls show (task 2.3) -------------------------------------------------------


@pytest.mark.usefixtures("shop")
def test_show_a_transcribed_call(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "show", "1"]) == 0
    text = capsys.readouterr().out
    assert "Call #1" in text
    assert "People: Nolan (Maybe, by name)" in text
    assert "Nolan: heard 'Nolan.' at 0:00" in text
    assert text.rstrip().endswith(
        "[0:00] Thanks for calling, this is Nolan.\n[0:05] I need brake pads."
    )
    shown = _json(["calls", "show", "1"], capsys)
    assert shown["call"]["id"] == 1
    assert [s["text"] for s in shown["transcript"]["segments"]] == [
        "Thanks for calling, this is Nolan.",
        "I need brake pads.",
    ]


def test_show_an_untranscribed_call(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    call_id = _listed(conn)
    assert main(["calls", "show", str(call_id)]) == 0
    text = capsys.readouterr().out
    assert "State: Not transcribed" in text
    assert text.rstrip().endswith("No transcript yet.")
    assert _json(["calls", "show", str(call_id)], capsys)["transcript"] is None


# --- calls transcribe (task 2.4) -------------------------------------------------


def test_transcribe_queues_a_not_transcribed_call(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    call_id = _listed(conn)
    assert _json(["calls", "transcribe", str(call_id)], capsys) == {
        "call_id": call_id,
        "queued": True,
        "state": "waiting",
    }
    jobs = conn.execute("SELECT count(*) FROM jobs WHERE call_id = ?", (call_id,)).fetchone()[0]
    assert jobs == 1


def test_transcribe_leaves_a_transcribed_call_alone(
    shop: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["calls", "transcribe", "1"]) == 0
    assert "left alone; it is Transcribed" in capsys.readouterr().out
    assert shop.execute("SELECT state FROM calls WHERE id = 1").fetchone()[0] == "transcribed"


@pytest.mark.usefixtures("conn")
def test_transcribe_an_unknown_call(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "transcribe", "999999"]) == 1
    assert "No call 999999 is listed." in capsys.readouterr().err
