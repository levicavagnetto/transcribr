import json
import sqlite3
from typing import Any

import pytest

from tests.api.conftest import Api
from transcribr.store.db import digits_only

ZONE_NOTE = "Store time is America/Chicago (UTC-5 in October)."


def add_call(
    conn: sqlite3.Connection,
    rid: int,
    start_local: str,
    *,
    state: str = "transcribed",
    caller: str = "(405) 555-0100",
    lines: list[str] | None = None,
    no_speech: bool = False,
    failure_reason: str | None = None,
    auto_queued: bool = True,
) -> None:
    """A call starting at start_local (store time); a transcript when lines are given."""
    day, clock = start_local.split(" ")
    hour = int(clock[:2]) + 5  # Chicago is UTC-5 in late October 2026
    start_utc = f"{day}T{hour:02d}{clock[2:]}Z"
    conn.execute(
        "INSERT INTO calls (id, queue, start_local, start_utc, minutes, caller_number,"
        " caller_digits, answered_by, listed_at, state, auto_queued, failure_reason)"
        " VALUES (?, 'tireProz-salescustserv', ?, ?, 2.5, ?, ?, 'SW Counter Sales', 't', ?, ?, ?)",
        (rid, start_local, start_utc, caller, digits_only(caller), state, int(auto_queued),
         failure_reason),
    )  # fmt: skip
    if lines is not None or no_speech:
        conn.execute(
            "INSERT INTO transcripts (call_id, language, model, transcribed_at, no_speech)"
            " VALUES (?, 'en', 'small.en', '2026-10-24T15:00:00Z', ?)",
            (rid, int(no_speech)),
        )
        for idx, text in enumerate(lines or []):
            conn.execute(
                "INSERT INTO segments (call_id, idx, start_s, end_s, speaker, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (rid, idx, idx * 10.0, idx * 10.0 + 8, f"Speaker {idx % 2 + 1}", text),
            )
        conn.execute(
            "INSERT INTO speakers (call_id, label, speech_seconds, fingerprint)"
            " VALUES (?, 'Speaker 1', 30.0, ?)",
            (rid, b"\x01\x02SECRET-FINGERPRINT-BYTES"),
        )


@pytest.fixture
def seeded(api: Api) -> Api:
    conn = api.db()
    add_call(
        conn,
        90000001,
        "2026-10-20 09:00:00",
        lines=["Thanks for calling.", "Do you have tires for a Camry?"],
    )
    lift_kit = ["Front counter.", "We want a lift kit for a Tacoma.", "And a lift kit quote."]
    add_call(conn, 90000002, "2026-10-22 10:30:00", caller="(405) 555-0142", lines=lift_kit)
    add_call(conn, 90000003, "2026-10-23 23:30:00", state="not_transcribed", caller="580.555.0142")
    add_call(conn, 90000004, "2026-10-24 08:15:00", state="waiting")
    add_call(conn, 90000005, "2026-10-24 08:45:00", state="failed",
             failure_reason="The recording from Ravon was incomplete.")  # fmt: skip
    add_call(conn, 90000006, "2026-10-24 09:10:00", no_speech=True)
    return api


def ids(response: Any) -> list[int]:
    assert response.status_code == 200, response.text
    return [c["id"] for c in response.json()["calls"]]


# --- 1.2: list, filters, paging ---------------------------------------------------------------


def test_lists_calls_newest_first(seeded: Api) -> None:
    body = seeded.client.get("/api/v1/calls").json()
    assert [c["id"] for c in body["calls"]] == [
        90000006,
        90000005,
        90000004,
        90000003,
        90000002,
        90000001,
    ]
    assert body["next_cursor"] is None
    first = body["calls"][0]
    assert first["state"] == "transcribed"
    assert first["no_speech"] is True
    assert first["passage"] is None


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("transcribed", [90000006, 90000002, 90000001]),
        ("waiting", [90000004]),
        ("not_transcribed", [90000003]),
        ("failed", [90000005]),
        ("processing", []),
    ],
)
def test_filters_by_state(seeded: Api, state: str, expected: list[int]) -> None:
    assert ids(seeded.client.get("/api/v1/calls", params={"state": state})) == expected


def test_an_unknown_state_is_refused(seeded: Api) -> None:
    response = seeded.client.get("/api/v1/calls", params={"state": "done"})
    assert response.status_code == 422


def test_dates_are_store_days(seeded: Api) -> None:
    # 23:30 on Oct 23 store time is already Oct 24 in UTC; it still belongs to Oct 23.
    assert ids(
        seeded.client.get("/api/v1/calls", params={"from": "2026-10-23", "to": "2026-10-23"})
    ) == [90000003]
    assert ids(seeded.client.get("/api/v1/calls", params={"from": "2026-10-22"})) == [
        90000006,
        90000005,
        90000004,
        90000003,
        90000002,
    ]
    assert ids(seeded.client.get("/api/v1/calls", params={"to": "2026-10-21"})) == [90000001]


def test_filters_combine(seeded: Api) -> None:
    params = {"state": "transcribed", "from": "2026-10-21", "to": "2026-10-23"}
    assert ids(seeded.client.get("/api/v1/calls", params=params)) == [90000002]


def test_pages_follow_the_cursor_and_ignore_new_calls(seeded: Api) -> None:
    first = seeded.client.get("/api/v1/calls", params={"limit": 2}).json()
    assert [c["id"] for c in first["calls"]] == [90000006, 90000005]
    assert first["next_cursor"]

    add_call(seeded.db(), 90000007, "2026-10-24 12:00:00")  # a new call arrives meanwhile

    second = seeded.client.get("/api/v1/calls", params={"limit": 2, "cursor": first["next_cursor"]})
    assert ids(second) == [90000004, 90000003]
    third = seeded.client.get(
        "/api/v1/calls", params={"limit": 2, "cursor": second.json()["next_cursor"]}
    ).json()
    assert [c["id"] for c in third["calls"]] == [90000002, 90000001]
    assert third["next_cursor"] is None


def test_a_bad_cursor_is_refused_clearly(seeded: Api) -> None:
    response = seeded.client.get("/api/v1/calls", params={"cursor": "not-a-cursor"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize("limit", [0, 201])
def test_the_page_size_is_bounded(seeded: Api, limit: int) -> None:
    assert seeded.client.get("/api/v1/calls", params={"limit": limit}).status_code == 422


# --- 1.3: text and number search --------------------------------------------------------------


def test_search_a_phrase_shows_the_first_matching_passage(seeded: Api) -> None:
    body = seeded.client.get("/api/v1/calls", params={"q": "lift kit"}).json()
    assert [c["id"] for c in body["calls"]] == [90000002]
    passage = body["calls"][0]["passage"]
    assert passage["at_s"] == 10.0  # the first of the two matching lines
    assert [p for p in passage["parts"] if p["hit"]] == [{"text": "lift kit", "hit": True}]
    assert "".join(p["text"] for p in passage["parts"]) == "We want a lift kit for a Tacoma."


def test_a_phrase_needs_its_words_together(seeded: Api) -> None:
    assert ids(seeded.client.get("/api/v1/calls", params={"q": "kit lift"})) == []


def test_search_ignores_case_and_punctuation(seeded: Api) -> None:
    assert ids(seeded.client.get("/api/v1/calls", params={"q": "CAMRY?"})) == [90000001]
    assert ids(seeded.client.get("/api/v1/calls", params={"q": '"tacoma"'})) == [90000002]


def test_a_query_without_words_does_not_filter(seeded: Api) -> None:
    assert len(ids(seeded.client.get("/api/v1/calls", params={"q": "?!"}))) == 6


@pytest.mark.parametrize("number", ["405 555 0142", "(405) 555-0142", "4055550142"])
def test_search_a_caller_number_in_any_format(seeded: Api, number: str) -> None:
    assert ids(seeded.client.get("/api/v1/calls", params={"number": number})) == [90000002]


def test_a_partial_number_matches_the_end_and_finds_untranscribed_calls(seeded: Api) -> None:
    assert ids(seeded.client.get("/api/v1/calls", params={"number": "555-0142"})) == [
        90000003,
        90000002,
    ]


def test_search_combines_with_filters(seeded: Api) -> None:
    params = {"number": "555-0142", "state": "not_transcribed"}
    assert ids(seeded.client.get("/api/v1/calls", params=params)) == [90000003]
    params = {"q": "lift kit", "to": "2026-10-21"}
    assert ids(seeded.client.get("/api/v1/calls", params=params)) == []


# --- 1.4: one call and its transcript ---------------------------------------------------------


def test_call_detail_for_each_state(seeded: Api) -> None:
    transcribed = seeded.client.get("/api/v1/calls/90000002").json()
    assert transcribed["state"] == "transcribed"
    assert transcribed["has_transcript"] is True
    assert transcribed["auto_queued"] is True
    assert transcribed["transcribed_at"] == "2026-10-24T15:00:00Z"
    assert (transcribed["language"], transcribed["model"]) == ("en", "small.en")
    assert transcribed["caller_number"] == "(405) 555-0142"

    missed = seeded.client.get("/api/v1/calls/90000003").json()
    assert (missed["state"], missed["has_transcript"], missed["transcribed_at"]) == (
        "not_transcribed",
        False,
        None,
    )
    failed = seeded.client.get("/api/v1/calls/90000005").json()
    assert failed["failure_reason"] == "The recording from Ravon was incomplete."
    assert seeded.client.get("/api/v1/calls/90000004").json()["state"] == "waiting"


def test_a_no_speech_call_has_an_empty_transcript(seeded: Api) -> None:
    detail = seeded.client.get("/api/v1/calls/90000006").json()
    assert (detail["state"], detail["no_speech"]) == ("transcribed", True)
    body = seeded.client.get("/api/v1/calls/90000006/transcript").json()
    assert body["no_speech"] is True
    assert body["segments"] == []


def test_the_transcript_has_timed_speaker_lines(seeded: Api) -> None:
    body = seeded.client.get("/api/v1/calls/90000002/transcript").json()
    assert body["speakers"] == ["Speaker 1"]
    assert body["segments"][1] == {
        "idx": 1,
        "start_s": 10.0,
        "end_s": 18.0,
        "speaker": "Speaker 2",
        "text": "We want a lift kit for a Tacoma.",
    }


def test_unknown_calls_and_missing_transcripts_say_which(seeded: Api) -> None:
    unknown = seeded.client.get("/api/v1/calls/12345678")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "call_not_found")
    unknown = seeded.client.get("/api/v1/calls/12345678/transcript")
    assert unknown.json()["error"]["code"] == "call_not_found"
    waiting = seeded.client.get("/api/v1/calls/90000004/transcript")
    assert (waiting.status_code, waiting.json()["error"]["code"]) == (404, "no_transcript")


def test_no_response_contains_fingerprint_data(seeded: Api) -> None:
    paths = [
        "/api/v1/calls",
        "/api/v1/calls?q=lift+kit",
        "/api/v1/calls/90000002",
        "/api/v1/calls/90000002/transcript",
        "/api/v1/calls/90000001/transcript",
    ]
    for path in paths:
        text = seeded.client.get(path).text
        assert "fingerprint" not in text.lower(), path
        assert "SECRET-FINGERPRINT" not in text, path
        json.loads(text)  # and every one is plain JSON
