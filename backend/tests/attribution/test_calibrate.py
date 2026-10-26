import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.attribution.conftest import add_call, voice
from transcribr.attribution.profiles import Profiles
from transcribr.attribution.voice import VoiceSamples
from transcribr.cli import main
from transcribr.ravon import client as ravon_client
from transcribr.store.db import connect
from transcribr.store.migrate import migrate

NOLAN = voice(1.0, 0.1)
CUSTOMER = voice(0.1, 1.0)
WORDS = "SECRET TRANSCRIPT WORDS"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(folder))
    return folder


@pytest.fixture
def seeded(data_dir: Path) -> Iterator[tuple[sqlite3.Connection, int]]:
    """Nolan enrolled from calls 1-3; call 4 has him for 6 s, call 5 is someone else."""
    migrate(data_dir / "transcribr.db")
    conn = connect(data_dir / "transcribr.db")
    nolan = Profiles(conn).create("Nolan", ["Nolan"]).id
    for call_id in (1, 2, 3):
        add_call(conn, call_id, [(0.0, 12.0, NOLAN)], text=WORDS)
        VoiceSamples(conn).add(nolan, call_id, [0])
    add_call(
        conn,
        4,
        [(0.0, 3.0, NOLAN), (3.5, 6.5, NOLAN), (7.0, 17.0, CUSTOMER), (17.5, 17.9, None)],
        text=WORDS,
    )
    add_call(conn, 5, [(0.0, 9.0, CUSTOMER)], text=WORDS)
    yield conn, nolan
    conn.close()


@pytest.fixture
def no_ravon(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("calibrate must not make any HTTP request or Ravon client")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(ravon_client.RavonClient, "__init__", refuse)


def test_calibrate_scores_stored_calls_and_writes_a_report(
    seeded: tuple[sqlite3.Connection, int],
    data_dir: Path,
    no_ravon: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, nolan = seeded
    assert main(["calibrate", "--profile", str(nolan), "--calls", "4", "5", "1"]) == 0

    out, err = capsys.readouterr()
    [report] = (data_dir / "reports").iterdir()
    assert report.name.startswith(f"calibration-profile{nolan}-") and report.suffix == ".csv"
    assert report.read_text(encoding="utf-8") == out
    assert f"Report written to {report}" in err
    rows = [line.split(",") for line in out.splitlines()]
    assert rows[0] == [
        "profile_id",
        "call_id",
        "voiced_seconds",
        "best_line_score",
        "presence_at_2s",
        "presence_at_4s",
        "presence_at_6s",
        "presence_at_8s",
        "enrolled",
    ]
    by_call = {row[1]: row for row in rows[1:]}
    assert list(by_call) == ["4", "5", "1"]
    # Call 4: 6 s of Nolan, then 10 s of the customer; the 0.4 s line has no voiceprint.
    assert by_call["4"][2] == "16.0"
    assert by_call["4"][3] == "1.000"
    assert by_call["4"][4:7] == ["1.000", "1.000", "1.000"]  # 2, 4 and 6 s fit in Nolan's 6 s
    assert float(by_call["4"][7]) < 0.5  # 8 s needs the customer's line
    assert by_call["4"][8] == "no"
    assert float(by_call["5"][5]) < 0.5
    assert by_call["1"][8] == "yes"

    everything = out + err + report.read_text(encoding="utf-8")
    assert "SECRET" not in everything and "TRANSCRIPT" not in everything
    assert "Nolan" not in everything


def test_too_little_voiceprinted_speech_leaves_the_presence_blank(
    seeded: tuple[sqlite3.Connection, int], no_ravon: None, capsys: pytest.CaptureFixture[str]
) -> None:
    conn, nolan = seeded
    add_call(conn, 6, [(0.0, 3.0, NOLAN), (3.0, 3.5, None)])
    assert main(["calibrate", "--profile", str(nolan), "--calls", "6"]) == 0
    row = capsys.readouterr().out.splitlines()[1].split(",")
    assert row[2:] == ["3.0", "1.000", "1.000", "", "", "", "no"]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--profile", "999", "--calls", "4"], "There is no such person."),
        (["--calls", "999"], "Call 999 has no transcript."),
    ],
)
def test_calibrate_explains_what_is_wrong(
    seeded: tuple[sqlite3.Connection, int],
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    _, nolan = seeded
    if "--profile" not in args:
        args = ["--profile", str(nolan), *args]
    assert main(["calibrate", *args]) == 1
    assert message in capsys.readouterr().err


def test_a_profile_without_enrolled_lines_cannot_be_calibrated(
    seeded: tuple[sqlite3.Connection, int], capsys: pytest.CaptureFixture[str]
) -> None:
    conn, _ = seeded
    dana = Profiles(conn).create("Dana", ["Dana"]).id
    assert main(["calibrate", "--profile", str(dana), "--calls", "4"]) == 1
    assert "Enroll some of this person's lines first." in capsys.readouterr().err
