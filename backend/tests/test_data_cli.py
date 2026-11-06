import argparse
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from transcribr import data_cli
from transcribr.attribution.profiles import Profiles
from transcribr.cli import build_parser, main
from transcribr.data_cli import CliError, find_person, require_call
from transcribr.ravon.parse import Recording
from transcribr.store.calls import add_listed
from transcribr.store.db import connect
from transcribr.store.migrate import migrate


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(folder))
    return folder


@pytest.fixture
def conn(data_dir: Path) -> Iterator[sqlite3.Connection]:
    migrate(data_dir / "transcribr.db")
    conn = connect(data_dir / "transcribr.db")
    yield conn
    conn.close()


def _add_call(conn: sqlite3.Connection, ravon_id: int = 90000001) -> int:
    add_listed(
        conn,
        Recording(ravon_id, "2026-11-05 08:00:00", 60.0, "(580) 555-0119", "SW Counter Sales"),
        queue="q",
        zone="America/Chicago",
        now=datetime(2026, 11, 5, 14, tzinfo=UTC),
        auto_queue=False,
    )
    return int(conn.execute("SELECT max(id) FROM calls").fetchone()[0])


# --- help (task 1.1) -----------------------------------------------------------


def _help(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(argv)
    assert exit_info.value.code == 0
    return capsys.readouterr().out


def test_calls_help_names_every_action(capsys: pytest.CaptureFixture[str]) -> None:
    text = _help(["calls", "--help"], capsys)
    for action in ("list", "search", "show", "transcribe"):
        assert action in text


def test_people_help_names_every_action(capsys: pytest.CaptureFixture[str]) -> None:
    text = _help(["people", "--help"], capsys)
    for action in ("list", "add", "claim", "confirm", "reject"):
        assert action in text


@pytest.mark.parametrize(
    "argv",
    [
        ["calls", "list"],
        ["calls", "search"],
        ["calls", "show"],
        ["calls", "transcribe"],
        ["people", "list"],
        ["people", "add"],
        ["people", "claim"],
        ["people", "confirm"],
        ["people", "reject"],
    ],
)
def test_each_action_has_an_example(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    text = _help([*argv, "--help"], capsys)
    assert "example:" in text
    assert f"docker compose exec web transcribr {argv[0]} {argv[1]}" in text
    assert "--json" in text


def test_top_level_help_lists_calls_and_people(capsys: pytest.CaptureFixture[str]) -> None:
    text = _help(["--help"], capsys)
    assert "calls" in text
    assert "people" in text


# --- lookups (task 1.2) ----------------------------------------------------------


def test_require_call_accepts_a_listed_call(conn: sqlite3.Connection) -> None:
    require_call(conn, _add_call(conn))


def test_require_call_rejects_an_unknown_call(conn: sqlite3.Connection) -> None:
    with pytest.raises(CliError) as error:
        require_call(conn, 999999)
    assert error.value.code == "call_not_found"
    assert "No call 999999 is listed" in error.value.message


def test_find_person_by_id_and_by_name_ignoring_case(conn: sqlite3.Connection) -> None:
    nolan = Profiles(conn).create("Nolan", ["Nolan"]).id
    assert find_person(conn, str(nolan)) == nolan
    assert find_person(conn, " nOLAN ") == nolan


def test_find_person_unknown_name(conn: sqlite3.Connection) -> None:
    with pytest.raises(CliError) as error:
        find_person(conn, "Bob")
    assert error.value.code == "person_not_found"
    assert error.value.message == "No person is named Bob."


def test_find_person_unknown_id(conn: sqlite3.Connection) -> None:
    with pytest.raises(CliError) as error:
        find_person(conn, "42")
    assert error.value.code == "person_not_found"


def test_find_person_shared_name_lists_the_ids(conn: sqlite3.Connection) -> None:
    first = Profiles(conn).create("Chris", ["Chris"]).id
    second = Profiles(conn).create("chris", ["Kris"]).id
    with pytest.raises(CliError) as error:
        find_person(conn, "Chris")
    assert error.value.code == "person_ambiguous"
    assert f"ids {first}, {second}" in error.value.message


# --- output and errors (task 1.2) ------------------------------------------------


@pytest.fixture
def echo_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for `calls show` until group 2 builds it: echo the call or fail as it will."""

    def handler(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[object, str]:
        require_call(conn, args.call_id)
        return {"id": args.call_id}, f"call {args.call_id}"

    monkeypatch.setitem(data_cli.HANDLERS, ("calls", "show"), handler)


@pytest.mark.usefixtures("echo_call")
def test_text_output_by_default(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    call_id = _add_call(conn)
    assert main(["calls", "show", str(call_id)]) == 0
    assert capsys.readouterr().out == f"call {call_id}\n"


@pytest.mark.usefixtures("echo_call")
def test_json_output_is_exactly_one_document(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    call_id = _add_call(conn)
    assert main(["calls", "show", str(call_id), "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"id": call_id}
    assert captured.err == ""


@pytest.mark.usefixtures("echo_call", "conn")
def test_an_unknown_call_exits_1_with_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "show", "999999"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No call 999999 is listed." in captured.err


@pytest.mark.usefixtures("echo_call", "conn")
def test_an_error_with_json_is_also_a_json_object(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "show", "999999", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "error": "call_not_found",
        "message": "No call 999999 is listed.",
    }
    assert "No call 999999 is listed." in captured.err


@pytest.mark.usefixtures("echo_call", "data_dir")
def test_without_a_database_it_explains(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["calls", "show", "1", "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"] == "no_database"
    assert "no Transcribr database" in captured.err
