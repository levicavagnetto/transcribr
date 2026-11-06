"""The `transcribr people ...` commands (add-data-cli group 3)."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from transcribr import data_cli
from transcribr.attribution.matching import rematch_all
from transcribr.attribution.profiles import Profiles
from transcribr.cli import main
from transcribr.store.db import connect
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


def _transcribed(conn: sqlite3.Connection, call_id: int, text: str) -> None:
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', '2026-11-05 08:00:00',"
        " '2026-11-05T14:00:00Z', 2, '(405) 555-0142', 'y', 't', 'transcribed')",
        (call_id,),
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (?, 'en', 'small.en', 't')",
        (call_id,),
    )
    conn.execute(
        "INSERT INTO segments (call_id, idx, start_s, end_s, text) VALUES (?, 0, 0, 4, ?)",
        (call_id, text),
    )
    conn.commit()


@pytest.fixture
def nolan(conn: sqlite3.Connection) -> int:
    """Nolan, a Maybe by name on call 1; call 2 has nobody."""
    _transcribed(conn, 1, "Thanks for calling, this is Nolan.")
    _transcribed(conn, 2, "Hello, how can I help?")
    profile_id = Profiles(conn).create("Nolan", ["Nolan", "Nolen"]).id
    rematch_all(conn, utcnow())
    return profile_id


def _json(argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    assert main([*argv, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def _status(conn: sqlite3.Connection, call_id: int, profile_id: int) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT status, method FROM attributions WHERE call_id = ? AND profile_id = ?",
        (call_id, profile_id),
    ).fetchone()
    return None if row is None else (row["status"], row["method"])


def test_every_command_is_built() -> None:
    assert set(data_cli.HANDLERS) == {
        ("calls", "list"),
        ("calls", "search"),
        ("calls", "show"),
        ("calls", "transcribe"),
        ("people", "list"),
        ("people", "add"),
        ("people", "claim"),
        ("people", "confirm"),
        ("people", "reject"),
    }


# --- people list and add (task 3.1) -----------------------------------------------


def test_list_shows_variants_and_counts(nolan: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert _json(["people", "list"], capsys) == {
        "people": [
            {
                "id": nolan,
                "display_name": "Nolan",
                "variants": ["Nolan", "Nolen"],
                "calls": 1,
                "maybe_calls": 1,
            }
        ]
    }
    assert main(["people", "list"]) == 0
    assert capsys.readouterr().out == (
        f"#{nolan}  Nolan  (heard as: Nolan, Nolen)  1 calls, 1 still Maybe\n"
    )


@pytest.mark.usefixtures("conn")
def test_list_with_nobody(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["people", "list"]) == 0
    assert capsys.readouterr().out == "Nobody has been added yet.\n"


def test_add_creates_the_person_and_queues_a_rematch(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    added = _json(["people", "add", "Sam", "--variant", "Sam", "--variant", "Sammy"], capsys)
    assert added["person"]["display_name"] == "Sam"
    assert added["person"]["variants"] == ["Sam", "Sammy"]
    assert conn.execute("SELECT count(*) FROM jobs WHERE type = 'rematch'").fetchone()[0] == 1


@pytest.mark.usefixtures("conn")
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["people", "add", "  ", "--variant", "Sam"], "name_required"),
        (["people", "add", "Sam", "--variant", "!!"], "variant_without_letters"),
        (["people", "add", "Sam", "--variant", "x" * 81], "variant_too_long"),
    ],
)
def test_add_gives_the_people_screen_errors(
    argv: list[str], code: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*argv, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == code


# --- claim, confirm and reject (task 3.2) -------------------------------------------


def test_confirm_makes_a_maybe_confident_by_hand(
    conn: sqlite3.Connection, nolan: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _status(conn, 1, nolan) == ("maybe", "name")
    result = _json(["people", "confirm", "nolan", "1"], capsys)
    assert _status(conn, 1, nolan) == ("confident", "manual")
    assert result["attributions"][0]["status"] == "confident"


def test_confirm_needs_a_maybe(nolan: int, capsys: pytest.CaptureFixture[str]) -> None:
    del nolan
    assert main(["people", "confirm", "Nolan", "2", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "not_maybe"


def test_claim_puts_the_person_on_a_call(
    conn: sqlite3.Connection, nolan: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["people", "claim", str(nolan), "2"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Nolan is now Confident on call #2.")
    assert "People: Nolan (Confident, set by hand)" in text
    assert _status(conn, 2, nolan) == ("confident", "manual")


def test_a_rejection_survives_a_rematch(
    conn: sqlite3.Connection, nolan: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _json(["people", "reject", "Nolan", "1"], capsys)["attributions"] == []
    rematch_all(conn, utcnow())
    assert _status(conn, 1, nolan) == ("rejected", "manual")


@pytest.mark.usefixtures("nolan")
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["people", "claim", "Bob", "1"], "person_not_found"),
        (["people", "claim", "Nolan", "999999"], "call_not_found"),
    ],
)
def test_unknown_person_or_call(
    argv: list[str], code: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*argv, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == code
