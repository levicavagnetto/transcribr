import logging
import tempfile
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from tests.clock import FakeClock
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.ravon.client import (
    AudioIncomplete,
    LoginRejected,
    NoCredentials,
    RavonClient,
    RavonUnavailable,
    credential_fingerprint,
)
from transcribr.ravon.guard import SEARCH_PATH, ReadOnlyViolation, search_form

BASE = "https://admin.ravon.net"
DAY = (datetime(2026, 10, 22, 0, 0), datetime(2026, 10, 23, 0, 0))


@pytest.fixture
def fake() -> FakeRavon:
    return FakeRavon(
        calls=[
            FakeCall(26541125, "tireProz-salescustserv", "2026-10-22 10:42:00", 6.2),
            FakeCall(26541126, "tireProz-salescustserv", "2026-10-22 11:05:30", 1.5),
            FakeCall(26541127, "tireProz-HDsales", "2026-10-22 11:10:00", 2.0),
        ]
    )


def make_client(
    fake: FakeRavon,
    clock: FakeClock | None = None,
    *,
    username: str | None = "admin@example.com",
    password: str | None = "correct-horse",
    rejected_fingerprint: str | None = None,
) -> RavonClient:
    return RavonClient(
        BASE,
        username,
        password,
        transport=httpx.MockTransport(fake.handle),
        clock=clock or FakeClock(),
        rejected_fingerprint=rejected_fingerprint,
    )


def paths(fake: FakeRavon) -> list[str]:
    return [f"{r.method} {r.url.path}" for r in fake.requests]


# --- 3.2 transport, pacing, backoff ----------------------------------------------------------


def test_requests_are_paced_at_least_a_second_apart(fake: FakeRavon) -> None:
    clock = FakeClock()
    client = make_client(fake, clock)
    client.search("tireProz-salescustserv", *DAY)
    client.search("tireProz-salescustserv", *DAY)
    # GET login, POST login, search, search: three gaps of a full second each.
    assert len(fake.requests) == 4
    assert sum(clock.sleeps) >= 3.0


def test_a_request_that_skips_the_helpers_is_still_refused(fake: FakeRavon) -> None:
    client = make_client(fake)
    form = {**search_form("q", *DAY), "checked": "26541125"}
    with pytest.raises(ReadOnlyViolation):
        client.http.post(SEARCH_PATH, data=form)
    with pytest.raises(ReadOnlyViolation):
        client.http.get("/ajax.html")
    assert fake.requests == []
    assert client.guard.violations == 2


def test_five_failures_start_an_increasing_backoff(fake: FakeRavon) -> None:
    clock = FakeClock()
    client = make_client(fake, clock)
    fake.server_errors = 5
    for _ in range(5):
        with pytest.raises(RavonUnavailable):
            client.queues()
    sent = len(fake.requests)

    with pytest.raises(RavonUnavailable, match="backing off"):
        client.queues()
    assert len(fake.requests) == sent  # nothing sent while backing off

    clock.advance(30)
    fake.server_errors = 1
    with pytest.raises(RavonUnavailable):
        client.queues()
    assert client.backoff_seconds == 60  # doubled after the sixth failure

    clock.advance(60)
    assert client.queues()  # recovers
    assert client.backoff_seconds == 0


def test_ravon_gets_a_minute_to_answer_but_ten_seconds_to_connect(fake: FakeRavon) -> None:
    timeout = make_client(fake).http.timeout
    assert timeout.connect == 10.0
    assert timeout.read == 60.0


def test_timeouts_count_as_failures(fake: FakeRavon) -> None:
    client = make_client(fake)
    fake.timeouts = 1
    with pytest.raises(RavonUnavailable, match="timed out"):
        client.queues()
    assert client.consecutive_failures == 1


def test_backoff_is_capped_at_ten_minutes(fake: FakeRavon) -> None:
    clock = FakeClock()
    client = make_client(fake, clock)
    for _ in range(12):
        fake.server_errors = 1
        with pytest.raises(RavonUnavailable):
            client.queues()
        clock.advance(client.backoff_seconds)
    assert client.backoff_seconds == 600


# --- 3.3 login ---------------------------------------------------------------------------


def test_logs_in_once_and_reuses_the_session(fake: FakeRavon) -> None:
    client = make_client(fake)
    client.search("tireProz-salescustserv", *DAY)
    client.queues()
    assert fake.logins == 1
    assert client.login_state == "ok"


def test_expired_session_logs_in_once_and_retries(fake: FakeRavon) -> None:
    client = make_client(fake)
    client.queues()
    fake.expire_sessions()
    assert client.queues()
    assert fake.logins == 2


def test_rejected_credentials_stop_further_attempts(fake: FakeRavon) -> None:
    fake.reject_logins = True
    client = make_client(fake)
    with pytest.raises(LoginRejected):
        client.queues()
    sent = len(fake.requests)
    with pytest.raises(LoginRejected):
        client.queues()
    assert len(fake.requests) == sent  # no second login attempt
    assert client.login_state == "rejected"


def test_retry_login_after_the_password_is_fixed_in_ravon(fake: FakeRavon) -> None:
    fake.reject_logins = True
    client = make_client(fake)
    with pytest.raises(LoginRejected):
        client.queues()
    fake.reject_logins = False
    client.retry_login()
    assert client.queues()
    assert client.login_state == "ok"


def test_changed_credentials_after_a_restart_are_tried(fake: FakeRavon) -> None:
    old = credential_fingerprint("admin@example.com", "old-password")
    client = make_client(fake, rejected_fingerprint=old)
    assert client.queues()  # new password, so a new attempt


def test_same_credentials_after_a_restart_are_not_retried(fake: FakeRavon) -> None:
    same = credential_fingerprint("admin@example.com", "correct-horse")
    client = make_client(fake, rejected_fingerprint=same)
    with pytest.raises(LoginRejected):
        client.queues()
    assert fake.requests == []


def test_no_credentials_means_no_contact(fake: FakeRavon) -> None:
    client = make_client(fake, username=None, password=None)
    with pytest.raises(NoCredentials):
        client.queues()
    assert fake.requests == []


def test_password_never_appears_in_logs(fake: FakeRavon, caplog: pytest.LogCaptureFixture) -> None:
    fake.reject_logins = True
    client = make_client(fake)
    with caplog.at_level(logging.DEBUG), pytest.raises(LoginRejected):
        client.queues()
    assert "correct-horse" not in caplog.text


# --- 3.4 search through the client ------------------------------------------------------------


def test_search_returns_the_queue_s_calls(fake: FakeRavon) -> None:
    client = make_client(fake)
    rows = client.search("tireProz-salescustserv", *DAY)
    assert [r.id for r in rows] == [26541125, 26541126]


def test_long_ranges_are_split_into_seven_day_searches(fake: FakeRavon) -> None:
    client = make_client(fake)
    client.search("tireProz-salescustserv", datetime(2026, 10, 1), datetime(2026, 10, 22, 12))
    searches = [r for r in fake.requests if r.method == "POST" and r.url.path == SEARCH_PATH]
    assert len(searches) == 4  # 21.5 days


def test_page_format_change_surfaces(fake: FakeRavon) -> None:
    from transcribr.ravon.parse import PageFormatChanged

    fake.page_format_changed = True
    with pytest.raises(PageFormatChanged):
        make_client(fake).search("tireProz-salescustserv", *DAY)


# --- 3.5 audio -------------------------------------------------------------------------------


def test_audio_for_a_listed_call_downloads_into_memory(fake: FakeRavon) -> None:
    client = make_client(fake)
    client.search("tireProz-salescustserv", *DAY)
    assert client.download(26541125) == b"ID3fake-mp3-bytes"


def test_audio_for_an_unlisted_call_is_refused(fake: FakeRavon) -> None:
    client = make_client(fake)
    with pytest.raises(ReadOnlyViolation):
        client.download(26541125)


def test_audio_known_from_the_database_is_allowed(fake: FakeRavon) -> None:
    client = RavonClient(
        BASE,
        "admin@example.com",
        "correct-horse",
        transport=httpx.MockTransport(fake.handle),
        clock=FakeClock(),
        is_known_recording=lambda rid: rid == 26541127,
    )
    assert client.download(26541127) == b"ID3fake-mp3-bytes"


def test_truncated_audio_fails(fake: FakeRavon) -> None:
    client = make_client(fake)
    client.search("tireProz-salescustserv", *DAY)
    fake.truncate_audio = True
    with pytest.raises(AudioIncomplete):
        client.download(26541125)


def test_downloads_leave_no_files_behind(
    fake: FakeRavon, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    client = make_client(fake)
    client.search("tireProz-salescustserv", *DAY)
    for rid in (26541125, 26541126):
        client.download(rid)
    leftovers = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert leftovers == []
