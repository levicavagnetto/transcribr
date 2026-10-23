import io
from datetime import date

import httpx
import pytest

from tests.clock import FakeClock
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.cli import main
from transcribr.config import load_config
from transcribr.ravon_check import ravon_check

ENV = {"RAVON_USERNAME": "admin@example.com", "RAVON_PASSWORD": "correct-horse"}
DAY = date(2026, 10, 21)


def fake_with_calls() -> FakeRavon:
    return FakeRavon(
        calls=[
            FakeCall(26541125, "tireProz-salescustserv", "2026-10-21 10:42:00", 6.2),
            FakeCall(26541126, "tireProz-salescustserv", "2026-10-21 16:05:30", 1.5),
            FakeCall(26541127, "tireProz-HDsales", "2026-10-21 11:10:00", 2.0),
            FakeCall(26541128, "tireProz-salescustserv", "2026-10-22 08:00:00", 2.0),
        ]
    )


def run(fake: FakeRavon, env: dict[str, str], queues: list[str] | None = None) -> tuple[int, str]:
    out = io.StringIO()
    code = ravon_check(
        load_config(env),
        day=DAY,
        queues=queues,
        out=out,
        transport=httpx.MockTransport(fake.handle),
        clock=FakeClock(),
    )
    return code, out.getvalue()


def test_counts_one_day_per_queue_without_downloading_audio() -> None:
    fake = fake_with_calls()
    code, text = run(fake, ENV)
    assert code == 0
    assert "Logged in to https://admin.ravon.net" in text
    assert "3 queues" in text
    assert "tireProz-salescustserv  Stillwater Sales/CS (x600)  2 calls" in text
    assert "tireProz-HDsales  Hudson Sales/CS (x700)  1 calls" in text
    assert "Total: 3 calls on 2026-10-21" in text
    assert not [r for r in fake.requests if r.url.path.startswith("/recordings/")]
    assert "555" not in text  # no caller numbers in the output


def test_one_queue_only() -> None:
    _, text = run(fake_with_calls(), ENV, ["tireProz-salescustserv"])
    assert "Total: 2 calls on 2026-10-21" in text


def test_rejected_login_is_explained() -> None:
    fake = fake_with_calls()
    fake.reject_logins = True
    code, text = run(fake, ENV)
    assert code == 1
    assert "rejected the username or password" in text


def test_missing_credentials_are_explained() -> None:
    code, text = run(fake_with_calls(), {})
    assert code == 1
    assert "RAVON_USERNAME" in text


def test_cli_lists_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["ravon-check", "--help"])
    assert "--day" in capsys.readouterr().out
