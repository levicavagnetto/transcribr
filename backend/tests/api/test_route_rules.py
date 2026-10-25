"""Rules that must hold for every route, checked by walking the app's real route list."""

import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from tests.api.conftest import WRITE, Api, make_api
from tests.fake_ravon.app import FakeCall, FakeRavon

# GET endpoints documented as reaching Ravon (spec web-app, "Reads have no side effects").
RAVON_GETS = {"/api/v1/calls/{call_id}/audio"}


def _walk(routes: Iterable[object]) -> Iterator[APIRoute]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        nested = getattr(route, "original_router", None)  # FastAPI's included-router wrapper
        if nested is not None:
            yield from _walk(nested.routes)


def api_routes(api: Api) -> list[tuple[str, str]]:
    app: FastAPI = api.client.app  # type: ignore[assignment]
    found: list[tuple[str, str]] = []
    for route in _walk(app.routes):
        if route.path.startswith("/api/"):
            found.extend((method, route.path) for method in sorted(route.methods or ()))
    return found


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "26541125", path)


def call(api: Api, method: str, path: str) -> httpx2.Response:
    return api.client.request(method, concrete(path), headers=WRITE, json={})


def snapshot(conn: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'segments_fts%'"
        )
    ]
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}  # noqa: S608


def test_the_route_list_is_not_empty(api: Api) -> None:
    routes = api_routes(api)
    assert ("GET", "/api/v1/admin/settings") in routes
    assert ("POST", "/api/v1/calls/{call_id}/transcribe") in routes


def test_every_admin_route_refuses_requests_without_a_session(api: Api) -> None:
    api.create_admin()
    api.client.cookies.clear()
    admin_routes = [(m, p) for m, p in api_routes(api) if p.startswith("/api/v1/admin/")]
    assert len(admin_routes) >= 6
    for method, path in admin_routes:
        response = call(api, method, path)
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"]["code"] == "admin_login_required"


def test_every_open_route_works_without_a_session(api: Api) -> None:
    api.create_admin()
    api.client.cookies.clear()
    open_routes = [(m, p) for m, p in api_routes(api) if not p.startswith("/api/v1/admin/")]
    for method, path in open_routes:
        response = call(api, method, path)
        assert response.status_code != 401, (method, path, response.text)


def test_every_get_changes_nothing_and_never_calls_out(
    admin: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_outbound(*_args: object, **_kwargs: object) -> httpx.Response:
        raise AssertionError("a GET endpoint tried to make an HTTP request")

    monkeypatch.setattr(httpx.Client, "send", no_outbound)
    conn = admin.db()
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number, answered_by,"
        " listed_at, state) VALUES (26541125, 'q', '2026-10-22 08:00:00', '2026-10-22T13:00:00Z',"
        " 2, 'x', 'y', 't', 'not_transcribed')"
    )
    before = snapshot(conn)
    gets = [p for m, p in api_routes(admin) if m == "GET"]
    assert set(gets) >= RAVON_GETS  # the exception list names real routes
    for path in gets:
        if path not in RAVON_GETS:
            admin.client.get(concrete(path))
    assert snapshot(admin.db()) == before


def test_the_gets_that_reach_ravon_say_so_and_change_nothing(tmp_path: Path) -> None:
    fake = FakeRavon(calls=[FakeCall(26541125, "q", "2026-10-22 08:00:00", 2.0)])
    env = {"RAVON_USERNAME": fake.username, "RAVON_PASSWORD": fake.password}
    for api in make_api(tmp_path, env, ravon_transport=httpx.MockTransport(fake.handle)):
        document = api.client.get("/api/v1/openapi.json").json()
        for path in RAVON_GETS:
            assert "sends a request to Ravon" in document["paths"][path]["get"]["description"]
        conn = api.db()
        conn.execute(
            "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
            " answered_by, listed_at, state) VALUES (26541125, 'q', '2026-10-22 08:00:00',"
            " '2026-10-22T13:00:00Z', 2, 'x', 'y', 't', 'transcribed')"
        )
        before = snapshot(conn)
        for path in RAVON_GETS:
            assert api.client.get(concrete(path)).status_code == 200
        assert snapshot(api.db()) == before
        assert {r.method for r in fake.requests} <= {"GET", "POST"}
        assert all(r.url.path in ("/auth/login", "/recordings/26541125") for r in fake.requests)


def test_the_openapi_document_covers_every_route(api: Api) -> None:
    document = api.client.get("/api/v1/openapi.json").json()
    for method, path in api_routes(api):
        if path in ("/api/v1/openapi.json", "/api/docs", "/api/docs/oauth2-redirect"):
            continue
        assert method.lower() in document["paths"].get(path, {}), (method, path)
        operation = document["paths"][path][method.lower()]
        assert "200" in operation["responses"], (method, path)
