import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from tests.api.conftest import Api, make_api
from transcribr.ingest.uptime import Uptime
from transcribr.settings import STORE_QUEUES, Settings
from transcribr.store.state import LAST_POLL_OK, RAVON_STATE, State
from transcribr.timeutil import to_iso

ENV = {"RAVON_USERNAME": "u@example.com", "RAVON_PASSWORD": "pw-for-tests"}


@pytest.fixture
def api_with_creds(tmp_path: Path) -> Iterator[Api]:
    yield from make_api(tmp_path, ENV)


def add_call(
    conn: sqlite3.Connection, rid: int, start_local: str, state: str, **extra: str
) -> None:
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number, answered_by,"
        " listed_at, state, failed_at)"
        " VALUES (?, 'q', ?, '2026-10-22T14:00:00Z', 2, 'x', 'y', 't', ?, ?)",
        (rid, start_local, state, extra.get("failed_at")),
    )


def test_status_reports_health_and_todays_counts(api_with_creds: Api) -> None:
    api = api_with_creds
    conn = api.db()
    now = api.clock.utcnow()  # 09:00 on 2026-10-22, store time
    Uptime(conn).heartbeat(now - timedelta(seconds=40))
    Settings(conn).set(STORE_QUEUES, ["tireProz-salescustserv"])
    State(conn).set(RAVON_STATE, "ok")
    State(conn).set(LAST_POLL_OK, to_iso(now - timedelta(minutes=1)))
    add_call(conn, 1, "2026-10-22 08:10:00", "transcribed")
    add_call(conn, 2, "2026-10-22 08:30:00", "transcribed")
    add_call(conn, 3, "2026-10-22 08:45:00", "waiting")
    add_call(conn, 4, "2026-10-22 08:50:00", "failed", failed_at=to_iso(now - timedelta(hours=2)))
    add_call(conn, 5, "2026-10-21 16:00:00", "failed", failed_at=to_iso(now - timedelta(hours=30)))

    status = api.client.get("/api/v1/status").json()

    assert status["worker_running"] is True
    assert status["ravon_state"] == "ok"
    assert status["ravon_error"] is None
    assert status["queues_chosen"] is True
    assert status["admin_exists"] is False
    assert (status["listed_today"], status["transcribed_today"]) == (4, 2)
    assert status["waiting"] == 1
    assert status["failed_last_24h"] == 1
    assert status["last_poll_ok"] == to_iso(now - timedelta(minutes=1))


def test_status_shows_a_stopped_worker(api_with_creds: Api) -> None:
    conn = api_with_creds.db()
    Uptime(conn).heartbeat(api_with_creds.clock.utcnow() - timedelta(minutes=3, seconds=1))
    assert api_with_creds.client.get("/api/v1/status").json()["worker_running"] is False


def test_status_without_credentials_says_so(api: Api) -> None:
    State(api.db()).set(RAVON_STATE, "ok")
    assert api.client.get("/api/v1/status").json()["ravon_state"] == "no_credentials"


def test_status_passes_on_the_ravon_error_when_not_ok(api_with_creds: Api) -> None:
    conn = api_with_creds.db()
    State(conn).set(RAVON_STATE, "login_failed")
    State(conn).set("ravon_error", "Ravon rejected the username or password")
    status = api_with_creds.client.get("/api/v1/status").json()
    assert status["ravon_state"] == "login_failed"
    assert status["ravon_error"] == "Ravon rejected the username or password"


def test_transcribe_queues_a_missed_call(api: Api) -> None:
    add_call(api.db(), 7, "2026-10-21 10:00:00", "not_transcribed")
    response = api.post("/api/v1/calls/7/transcribe")
    assert response.status_code == 200
    assert response.json() == {"queued": True, "state": "waiting"}
    assert api.db().execute("SELECT count(*) FROM jobs WHERE call_id = 7").fetchone()[0] == 1


def test_transcribe_twice_creates_one_job(api: Api) -> None:
    add_call(api.db(), 7, "2026-10-21 10:00:00", "not_transcribed")
    api.post("/api/v1/calls/7/transcribe")
    response = api.post("/api/v1/calls/7/transcribe")
    assert response.json() == {"queued": False, "state": "waiting"}
    assert api.db().execute("SELECT count(*) FROM jobs WHERE call_id = 7").fetchone()[0] == 1


def test_transcribe_an_unknown_call_is_404(api: Api) -> None:
    response = api.post("/api/v1/calls/99999999/transcribe")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "call_not_found"


def test_load_earlier_asks_the_worker_once(api: Api) -> None:
    for _ in range(3):
        assert api.post("/api/v1/calls/load-earlier").json() == {"requested": True}
    jobs = api.db().execute("SELECT count(*) FROM jobs WHERE type = 'load_earlier'").fetchone()[0]
    assert jobs == 1
