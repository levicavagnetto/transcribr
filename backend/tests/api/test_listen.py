from collections.abc import Iterator
from pathlib import Path

import httpx
import httpx2
import pytest

from tests.api.conftest import Api, make_api
from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.ravon.client import credential_fingerprint
from transcribr.store.state import RAVON_REJECTED_FINGERPRINT, State

CALL = 90000002
AUDIO = b"ID3" + bytes(range(256)) * 40  # stands in for an MP3


class Listen:
    def __init__(self, api: Api, fake: FakeRavon) -> None:
        self.api = api
        self.fake = fake

    def get(self, call_id: int = CALL) -> httpx2.Response:
        return self.api.client.get(f"/api/v1/calls/{call_id}/audio")


def listed(api: Api, call_id: int = CALL) -> None:
    api.db().execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', '2026-10-22 08:00:00',"
        " '2026-10-22T13:00:00Z', 2, 'x', 'y', 't', 'transcribed')",
        (call_id,),
    )


def make_listen(tmp_path: Path, env: dict[str, str]) -> Iterator[Listen]:
    fake = FakeRavon(calls=[FakeCall(CALL, "q", "2026-10-22 08:00:00", 2.0, audio=AUDIO)])
    for api in make_api(tmp_path, env, ravon_transport=httpx.MockTransport(fake.handle)):
        listed(api)
        yield Listen(api, fake)


@pytest.fixture
def listen(tmp_path: Path) -> Iterator[Listen]:
    fake = FakeRavon()
    env = {"RAVON_USERNAME": fake.username, "RAVON_PASSWORD": fake.password}
    yield from make_listen(tmp_path, env)


def test_plays_the_recording_through_the_server(listen: Listen) -> None:
    response = listen.get()
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["content-length"] == str(len(AUDIO))
    assert response.headers["cache-control"] == "no-store"
    assert response.content == AUDIO
    assert listen.fake.logins == 1
    assert listen.get().content == AUDIO
    assert listen.fake.logins == 1  # the session is reused


def test_an_unlisted_call_never_reaches_ravon(listen: Listen) -> None:
    response = listen.get(12345678)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "call_not_found")
    assert listen.fake.requests == []


def test_ravon_down_says_so(listen: Listen) -> None:
    listen.fake.server_errors = 3
    response = listen.get()
    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "ravon_unavailable",
        "message": "The recording can't be fetched from Ravon right now.",
    }


def test_a_truncated_recording_is_not_played(listen: Listen) -> None:
    listen.fake.truncate_audio = True
    response = listen.get()
    assert (response.status_code, response.json()["error"]["code"]) == (502, "ravon_unavailable")


def test_a_rejected_login_says_so(listen: Listen) -> None:
    listen.fake.reject_logins = True
    response = listen.get()
    assert (response.status_code, response.json()["error"]["code"]) == (502, "ravon_login_failed")


def test_a_login_the_worker_found_rejected_is_not_tried_until_retried(listen: Listen) -> None:
    fake = listen.fake
    State(listen.api.db()).set(
        RAVON_REJECTED_FINGERPRINT, credential_fingerprint(fake.username, fake.password)
    )
    assert listen.get().json()["error"]["code"] == "ravon_login_failed"
    assert fake.logins == 0

    State(listen.api.db()).delete(RAVON_REJECTED_FINGERPRINT)  # the worker's retry worked
    assert listen.get().status_code == 200


def test_missing_credentials_say_so(tmp_path: Path) -> None:
    for listen in make_listen(tmp_path, {}):
        response = listen.get()
        assert (response.status_code, response.json()["error"]["code"]) == (
            502,
            "ravon_no_credentials",
        )
        assert listen.fake.requests == []


def test_no_audio_is_left_on_disk(listen: Listen, tmp_path: Path) -> None:
    assert listen.get().status_code == 200
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert AUDIO[:64] not in path.read_bytes(), path
            assert path.suffix.lower() not in {".mp3", ".wav"}, path
