"""The people and attribution endpoints (add-call-attribution 5.1 to 5.3, 8.4)."""

import sqlite3
from typing import Any

import pytest

from tests.api.conftest import Api
from transcribr.attribution.matching import rematch_all
from transcribr.timeutil import utcnow


def add_call(
    conn: sqlite3.Connection,
    rid: int,
    hour: int,
    lines: list[tuple[str, float]],
) -> None:
    """A Transcribed call on 2026-10-22 at `hour`:00 store time, with (text, seconds) lines."""
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at, state) VALUES (?, 'q', ?, ?, 2, '(405) 555-0100', 'y', 't',"
        " 'transcribed')",
        (rid, f"2026-10-22 {hour:02d}:00:00", f"2026-10-22T{hour + 5:02d}:00:00Z"),
    )
    conn.execute(
        "INSERT INTO transcripts (call_id, language, model, transcribed_at)"
        " VALUES (?, 'en', 'small.en', 't')",
        (rid,),
    )
    at = 0.0
    for idx, (text, seconds) in enumerate(lines):
        conn.execute(
            "INSERT INTO segments (call_id, idx, start_s, end_s, text) VALUES (?, ?, ?, ?, ?)",
            (rid, idx, at, at + seconds, text),
        )
        at += seconds + 0.5


@pytest.fixture
def calls(api: Api) -> Api:
    conn = api.db()
    add_call(conn, 1, 8, [("Tire Pros, this is Nolan.", 3.0), ("I need a lift kit quote.", 5.0)])
    add_call(conn, 2, 9, [("Front counter.", 2.0), ("A lift kit please.", 4.0)])
    add_call(conn, 3, 10, [("Is Nolan there?", 3.0), ("Hello?", 0.6)])
    add_call(conn, 4, 11, [("Tires for a Camry.", 6.0)])
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " answered_by, listed_at) VALUES (5, 'q', '2026-10-22 12:00:00', '2026-10-22T17:00:00Z',"
        " 1, 'x', 'y', 't')"
    )
    return api


def nolan(api: Api) -> int:
    response = api.post(
        "/api/v1/admin/profiles", json={"display_name": "Nolan", "variants": ["Nolan", "Nolen"]}
    )
    assert response.status_code == 200, response.text
    profile_id: int = response.json()["id"]
    return profile_id


def rematch(api: Api) -> None:
    rematch_all(api.db(), utcnow())


def ids(api: Api, **params: Any) -> list[int]:
    response = api.client.get("/api/v1/calls", params=params)
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()["calls"]]


# --- 5.1 admin profiles -----------------------------------------------------------------------


def test_the_admin_manages_profiles(calls: Api) -> None:
    calls.create_admin()
    calls.login()
    created = calls.post(
        "/api/v1/admin/profiles", json={"display_name": "Nolan", "variants": ["Nolan", "Nolen"]}
    ).json()
    assert created["variants"] == ["Nolan", "Nolen"]
    assert created["found"] == {"name": 0, "manual": 0, "maybe": 0}
    assert "voice" not in created

    pid = created["id"]
    edited = calls.put(
        f"/api/v1/admin/profiles/{pid}", json={"display_name": "Nolan B.", "variants": ["Nolan"]}
    )
    assert (edited.json()["display_name"], edited.json()["variants"]) == ("Nolan B.", ["Nolan"])
    assert calls.client.get(f"/api/v1/admin/profiles/{pid}").json()["display_name"] == "Nolan B."
    listed = calls.client.get("/api/v1/admin/profiles").json()["profiles"]
    assert [p["id"] for p in listed] == [pid]

    assert calls.client.delete(
        f"/api/v1/admin/profiles/{pid}", headers={"X-Transcribr": "1"}
    ).json() == {"deleted": True}
    assert calls.client.get("/api/v1/admin/profiles").json()["profiles"] == []


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"display_name": " ", "variants": ["Nolan"]}, 422, "name_required"),
        ({"display_name": "Nolan", "variants": []}, 422, "variant_required"),
        ({"display_name": "Nolan"}, 422, "invalid_request"),
    ],
)
def test_bad_profiles_are_refused(admin: Api, body: dict[str, Any], status: int, code: str) -> None:
    response = admin.post("/api/v1/admin/profiles", json=body)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)


def test_unknown_profiles_are_404(admin: Api) -> None:
    for response in (
        admin.client.get("/api/v1/admin/profiles/99"),
        admin.put("/api/v1/admin/profiles/99", json={"display_name": "X", "variants": ["X"]}),
        admin.client.delete("/api/v1/admin/profiles/99", headers={"X-Transcribr": "1"}),
    ):
        assert (response.status_code, response.json()["error"]["code"]) == (
            404,
            "profile_not_found",
        )


def test_profiles_are_refused_without_an_admin_session(calls: Api) -> None:
    calls.create_admin()
    calls.login()
    pid = nolan(calls)
    calls.client.cookies.clear()
    for response in (
        calls.client.get("/api/v1/admin/profiles"),
        calls.client.get(f"/api/v1/admin/profiles/{pid}"),
    ):
        assert response.status_code == 401
        assert "Nolan" not in response.text


# --- 5.2 open call actions --------------------------------------------------------------------


def test_claim_reject_and_confirm_without_logging_in(calls: Api) -> None:
    calls.create_admin()
    calls.login()
    pid = nolan(calls)
    calls.client.cookies.clear()

    claimed = calls.post("/api/v1/calls/4/attributions", json={"profile_id": pid})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json() == {
        "attributions": [
            {"profile_id": pid, "display_name": "Nolan", "status": "confident", "method": "manual",
             "name_heard": None, "name_at_s": None}
        ]
    }  # fmt: skip

    rematch(calls)  # call 3: "Is Nolan there?" -> Maybe by name
    rejected = calls.client.delete(
        f"/api/v1/calls/3/attributions/{pid}", headers={"X-Transcribr": "1"}
    )
    assert rejected.json() == {"attributions": []}
    rematch(calls)
    assert ids(calls, person=pid) == [4, 1]  # 3 stays rejected

    conn = calls.db()
    conn.execute(
        "UPDATE attributions SET status = 'maybe', method = 'name'"
        " WHERE call_id = 1 AND profile_id = ?",
        (pid,),
    )
    confirmed = calls.post(f"/api/v1/calls/1/attributions/{pid}/confirm")
    assert confirmed.json()["attributions"][0]["status"] == "confident"
    assert confirmed.json()["attributions"][0]["method"] == "manual"
    again = calls.post(f"/api/v1/calls/1/attributions/{pid}/confirm")
    assert (again.status_code, again.json()["error"]["code"]) == (409, "not_maybe")


@pytest.mark.parametrize(
    ("method", "path", "code"),
    [
        ("POST", "/api/v1/calls/999/attributions", "call_not_found"),
        ("DELETE", "/api/v1/calls/999/attributions/{pid}", "call_not_found"),
        ("POST", "/api/v1/calls/999/attributions/{pid}/confirm", "call_not_found"),
        ("DELETE", "/api/v1/calls/1/attributions/999", "profile_not_found"),
    ],
)
def test_call_actions_on_unknown_calls_or_people(
    calls: Api, method: str, path: str, code: str
) -> None:
    calls.create_admin()
    calls.login()
    pid = nolan(calls)
    response = calls.client.request(
        method, path.format(pid=pid), json={"profile_id": pid}, headers={"X-Transcribr": "1"}
    )
    assert (response.status_code, response.json()["error"]["code"]) == (404, code)


# --- 5.3 person filters in the call list ------------------------------------------------------


@pytest.fixture
def attributed(calls: Api) -> tuple[Api, int, int]:
    """Nolan: Confident on 1 (confirmed), Maybe on 2 (name). Dana: Confident on 2 (manual)."""
    calls.create_admin()
    calls.login()
    pid = nolan(calls)
    dana = calls.post(
        "/api/v1/admin/profiles", json={"display_name": "Dana", "variants": ["Dana"]}
    ).json()["id"]
    conn = calls.db()
    conn.executemany(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, name_heard,"
        " name_at_s, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 't')",
        [
            (1, pid, "confident", "manual", "manual", "Nolan.", 1.6),
            (2, pid, "maybe", "auto", "name", "Nolen", 0.4),
            (2, dana, "confident", "manual", "manual", None, None),
            (3, pid, "rejected", "manual", "manual", None, None),
        ],
    )
    calls.client.cookies.clear()  # everything below is open
    return calls, pid, dana


def test_filter_to_one_person(attributed: tuple[Api, int, int]) -> None:
    api, pid, dana = attributed
    assert ids(api, person=pid) == [2, 1]
    assert ids(api, person=dana) == [2]
    assert ids(api, person=999) == []
    body = api.client.get("/api/v1/calls", params={"person": pid}).json()
    marks = {
        c["id"]: [(a["display_name"], a["status"]) for a in c["attributions"]]
        for c in body["calls"]
    }
    assert marks == {2: [("Dana", "confident"), ("Nolan", "maybe")], 1: [("Nolan", "confident")]}
    first = body["calls"][1]["attributions"][0]
    assert (first["method"], first["name_heard"], first["name_at_s"]) == ("manual", "Nolan.", 1.6)


def test_review_uncertain_calls(attributed: tuple[Api, int, int]) -> None:
    api, pid, dana = attributed
    assert ids(api, maybe="true") == [2]
    assert ids(api, person=pid, maybe="true") == [2]
    assert ids(api, person=dana, maybe="true") == []


def test_unassigned_calls(attributed: tuple[Api, int, int]) -> None:
    api, pid, _ = attributed
    assert ids(api, unassigned="true") == [4, 3]  # 3 was rejected; 5 isn't transcribed
    refused = api.client.get("/api/v1/calls", params={"unassigned": "true", "person": pid})
    assert (refused.status_code, refused.json()["error"]["code"]) == (422, "invalid_filter")


def test_search_within_a_persons_calls(attributed: tuple[Api, int, int]) -> None:
    api, pid, _ = attributed
    assert ids(api, q="lift kit") == [2, 1]
    assert ids(api, person=pid, q="lift kit") == [2, 1]
    assert ids(api, person=pid, q="Camry") == []
    assert ids(api, unassigned="true", q="Camry") == [4]


def test_list_a_persons_calls_since_a_time_in_pages(attributed: tuple[Api, int, int]) -> None:
    api, pid, _ = attributed
    params: dict[str, Any] = {"person": pid, "since": "2026-10-22T12:30:00Z", "limit": 1}
    first = api.client.get("/api/v1/calls", params=params).json()
    assert [c["id"] for c in first["calls"]] == [2]
    assert first["calls"][0]["attributions"]
    second = api.client.get(
        "/api/v1/calls", params={**params, "cursor": first["next_cursor"]}
    ).json()
    assert [c["id"] for c in second["calls"]] == [1]
    assert second["next_cursor"] is None
    later = api.client.get("/api/v1/calls", params={"person": pid, "since": "2026-10-22T13:30:00Z"})
    assert [c["id"] for c in later.json()["calls"]] == [2]


def test_people_for_the_filters(attributed: tuple[Api, int, int]) -> None:
    api, pid, dana = attributed
    assert api.client.get("/api/v1/people").json() == {
        "people": [
            {"id": dana, "display_name": "Dana", "calls": 1, "maybe_calls": 0},
            {"id": pid, "display_name": "Nolan", "calls": 2, "maybe_calls": 1},
        ],
        "maybe_calls": 1,
        "unassigned_calls": 2,
    }


def test_the_call_screen_gets_the_calls_attributions(attributed: tuple[Api, int, int]) -> None:
    api, _, _ = attributed
    detail = api.client.get("/api/v1/calls/2").json()
    assert [(a["display_name"], a["status"], a["name_heard"]) for a in detail["attributions"]] == [
        ("Dana", "confident", None),
        ("Nolan", "maybe", "Nolen"),
    ]
    assert api.client.get("/api/v1/calls/3").json()["attributions"] == []  # rejections are hidden


def test_no_voice_field_appears_in_any_response(attributed: tuple[Api, int, int]) -> None:
    api, pid, _ = attributed
    api.login()
    paths = [
        "/api/v1/calls",
        f"/api/v1/calls?person={pid}",
        "/api/v1/calls/1",
        "/api/v1/calls/1/transcript",
        "/api/v1/people",
        "/api/v1/admin/profiles",
        f"/api/v1/admin/profiles/{pid}",
    ]
    for path in paths:
        response = api.client.get(path)
        assert response.status_code == 200, path
        assert "voice" not in response.text.lower(), path
    assert api.client.get(f"/api/v1/admin/profiles/{pid}/samples").status_code == 404
