from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.api.conftest import Api, make_api
from transcribr.store.state import (
    QUEUE_LIST,
    QUEUE_REFRESH_REQUESTED,
    RETRY_LOGIN_REQUESTED,
    State,
)

SECRET = "the-real-ravon-password"


@pytest.fixture
def admin_with_creds(tmp_path: Path) -> Iterator[Api]:
    for api in make_api(tmp_path, {"RAVON_USERNAME": "u@example.com", "RAVON_PASSWORD": SECRET}):
        api.create_admin()
        yield api


def test_settings_show_values_and_labels(admin: Api) -> None:
    body = admin.client.get("/api/v1/admin/settings").json()
    assert body["values"]["poll_interval_minutes"] == 2
    assert body["values"]["time_zone"] == "America/Chicago"
    assert body["values"]["store_queues"] == []
    assert {"key": "poll_interval_minutes", "label": "Check for new calls every (minutes)"} in body[
        "fields"
    ]


def test_settings_change_and_are_returned(admin: Api) -> None:
    response = admin.put(
        "/api/v1/admin/settings",
        json={"poll_interval_minutes": 5, "store_queues": ["tireProz-salescustserv"]},
    )
    assert response.status_code == 200
    assert response.json()["values"]["poll_interval_minutes"] == 5
    assert response.json()["values"]["store_queues"] == ["tireProz-salescustserv"]


def test_an_invalid_value_is_refused_with_its_message_and_nothing_changes(admin: Api) -> None:
    response = admin.put(
        "/api/v1/admin/settings", json={"time_zone": "America/Denver", "poll_interval_minutes": 0}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_setting"
    assert error["key"] == "poll_interval_minutes"
    assert "between 1 and 30" in error["message"]
    values = admin.client.get("/api/v1/admin/settings").json()["values"]
    assert values["time_zone"] == "America/Chicago"  # all-or-nothing


def test_an_unknown_setting_is_refused(admin: Api) -> None:
    response = admin.put("/api/v1/admin/settings", json={"favourite_colour": "orange"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_setting"


def test_queues_come_from_the_worker_cache(admin: Api) -> None:
    empty = admin.client.get("/api/v1/admin/queues").json()
    assert empty == {"queues": [], "fetched_at": None, "refresh_requested": False}
    State(admin.db()).set(
        QUEUE_LIST,
        {
            "fetched_at": "2026-10-22T14:00:00Z",
            "queues": [{"value": "tireProz-salescustserv", "label": "Stillwater Sales/CS (x600)"}],
        },
    )
    body = admin.client.get("/api/v1/admin/queues").json()
    assert body["queues"][0]["label"] == "Stillwater Sales/CS (x600)"
    assert body["fetched_at"] == "2026-10-22T14:00:00Z"


def test_refresh_and_retry_login_are_requests_to_the_worker(admin: Api) -> None:
    assert admin.post("/api/v1/admin/queues/refresh").json() == {"requested": True}
    assert admin.post("/api/v1/admin/ravon/retry-login").json() == {"requested": True}
    state = State(admin.db())
    assert state.get(QUEUE_REFRESH_REQUESTED) is True
    assert state.get(RETRY_LOGIN_REQUESTED) is True
    assert admin.client.get("/api/v1/admin/queues").json()["refresh_requested"] is True


def test_the_ravon_password_never_appears(admin_with_creds: Api) -> None:
    api = admin_with_creds
    for path in (
        "/api/v1/admin/settings",
        "/api/v1/status",
        "/api/v1/admin/queues",
        "/api/v1/auth/state",
    ):
        assert SECRET not in api.client.get(path).text
    assert SECRET not in api.client.get("/api/v1/openapi.json").text
