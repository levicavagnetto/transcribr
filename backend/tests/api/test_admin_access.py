import logging

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import WRITE, Api

PASSWORD = "workbench-lift-35s"


def test_first_visit_needs_setup(api: Api) -> None:
    assert api.client.get("/api/v1/auth/state").json() == {
        "state": "setup_required",
        "username": None,
    }
    assert len(api.setup_codes) == 1
    assert len(api.setup_code) == 12  # XXXX-XXXX-XX


def test_setup_with_the_code_creates_the_admin_and_logs_in(api: Api) -> None:
    response = api.post(
        "/api/v1/auth/setup",
        json={
            "code": api.setup_code.lower().replace("-", ""),
            "username": "admin",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"state": "logged_in", "username": "admin"}
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=43200" in cookie
    assert api.client.get("/api/v1/admin/settings").status_code == 200


def test_a_wrong_setup_code_creates_nothing(api: Api) -> None:
    response = api.post(
        "/api/v1/auth/setup",
        json={"code": "AAAA-BBBB-CC", "username": "admin", "password": PASSWORD},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "wrong_setup_code"
    assert api.client.get("/api/v1/auth/state").json()["state"] == "setup_required"


def test_the_code_is_used_up_once_the_admin_exists(api: Api) -> None:
    code = api.setup_code
    api.create_admin()
    again = api.post(
        "/api/v1/auth/setup", json={"code": code, "username": "x", "password": PASSWORD}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "admin_exists"
    assert api.db().execute("SELECT count(*) FROM admin_setup_code").fetchone()[0] == 0


def test_a_short_password_is_refused(api: Api) -> None:
    response = api.post(
        "/api/v1/auth/setup",
        json={"code": api.setup_code, "username": "admin", "password": "short-pw"},
    )
    assert response.status_code == 422
    assert "at least 12 characters" in response.json()["error"]["message"]


def test_admin_endpoints_need_a_session(api: Api) -> None:
    api.create_admin()
    api.client.cookies.clear()
    response = api.client.get("/api/v1/admin/settings")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "admin_login_required", "message": "Log in as the admin first."}
    }


def test_login_and_logout(api: Api) -> None:
    api.create_admin()
    api.client.cookies.clear()
    api.login()
    assert api.client.get("/api/v1/auth/state").json()["state"] == "logged_in"
    assert api.post("/api/v1/auth/logout").json()["state"] == "login_required"
    assert api.client.get("/api/v1/admin/settings").status_code == 401


def test_a_logged_out_token_stops_working_on_the_server(api: Api) -> None:
    api.create_admin()
    token = api.client.cookies.get("transcribr_admin")
    api.post("/api/v1/auth/logout")
    api.client.cookies.set("transcribr_admin", token or "")
    response = api.client.get("/api/v1/admin/settings")
    assert response.status_code == 401


def test_sessions_expire_after_twelve_hours(admin: Api) -> None:
    admin.clock.advance(12 * 3600 - 60)
    assert admin.client.get("/api/v1/admin/settings").status_code == 200
    admin.clock.advance(120)
    assert admin.client.get("/api/v1/admin/settings").status_code == 401


def test_admin_writes_need_the_request_header(admin: Api) -> None:
    response = admin.client.put("/api/v1/admin/settings", json={"poll_interval_minutes": 5})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "missing_request_header"


def test_wrong_logins_are_slowed_down_and_logged_without_passwords(
    api: Api, caplog: pytest.LogCaptureFixture
) -> None:
    api.create_admin()
    api.client.cookies.clear()
    with caplog.at_level(logging.WARNING):
        for attempt in range(5):
            response = api.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": f"guess-number-{attempt}"},
            )
            assert response.status_code == 401
    blocked = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["retry_after"] == 30
    assert "guess-number" not in caplog.text
    assert caplog.text.count("failed admin login") == 5

    api.clock.advance(31)
    api.login()  # the right password works once the block has passed


def test_wrong_setup_codes_are_slowed_down_too(api: Api) -> None:
    for _ in range(5):
        api.post(
            "/api/v1/auth/setup", json={"code": "WRONG", "username": "a", "password": PASSWORD}
        )
    response = api.post(
        "/api/v1/auth/setup", json={"code": api.setup_code, "username": "a", "password": PASSWORD}
    )
    assert response.status_code == 429


def test_change_password_ends_other_sessions(admin: Api) -> None:
    other = TestClient(admin.client.app)
    other.post(
        "/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}, headers=WRITE
    )
    assert other.get("/api/v1/admin/settings").status_code == 200

    response = admin.post(
        "/api/v1/admin/password", json={"current": PASSWORD, "new": "a-brand-new-passphrase"}
    )
    assert response.status_code == 200
    assert admin.client.get("/api/v1/admin/settings").status_code == 200  # this session stays
    assert other.get("/api/v1/admin/settings").status_code == 401  # others end

    admin.client.cookies.clear()
    bad = admin.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert bad.status_code == 401
    admin.login(password="a-brand-new-passphrase")


def test_change_password_needs_the_current_one(admin: Api) -> None:
    response = admin.post(
        "/api/v1/admin/password",
        json={"current": "not-the-password", "new": "a-brand-new-passphrase"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "wrong_password"


def test_no_response_contains_the_password_hash(admin: Api) -> None:
    hashed = admin.db().execute("SELECT password_hash FROM admin").fetchone()[0]
    for path in ("/api/v1/auth/state", "/api/v1/admin/settings", "/api/v1/status"):
        assert hashed not in admin.client.get(path).text
