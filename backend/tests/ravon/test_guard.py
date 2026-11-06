import logging
import re
from datetime import datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from transcribr.ravon.guard import (
    SEARCH_FIELDS,
    SEARCH_PATH,
    Guard,
    ReadOnlyViolation,
    search_form,
)

BASE = "https://admin.ravon.net"
KNOWN_ID = 26541125


def guard() -> Guard:
    return Guard(BASE, is_known_recording=lambda rid: rid == KNOWN_ID)


def good_search() -> dict[str, str]:
    return search_form(
        "tireProz-salescustserv", datetime(2026, 10, 21, 0, 0), datetime(2026, 10, 22, 0, 0)
    )


# --- allowed -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "form"),
    [
        ("GET", "/auth/login", None),
        ("POST", "/auth/login", {"username": "u@example.com", "password": "pw"}),
        ("GET", SEARCH_PATH, None),
        ("POST", SEARCH_PATH, good_search()),
        ("GET", f"/recordings/{KNOWN_ID}", None),
    ],
)
def test_allowed_requests(method: str, path: str, form: dict[str, str] | None) -> None:
    guard().check(method, BASE + path, form)


def test_search_form_has_exactly_the_eight_fields() -> None:
    assert set(good_search()) == SEARCH_FIELDS
    assert good_search()["query"] == "Find Calls"
    assert good_search()["startDate"] == "2026-10-21 00:00:00"


def test_seven_day_search_is_allowed() -> None:
    start = datetime(2026, 10, 1)
    guard().check("POST", BASE + SEARCH_PATH, search_form("q", start, start + timedelta(days=7)))


# --- refused -------------------------------------------------------------------------------


def refused(method: str, url: str, form: dict[str, str] | None = None) -> None:
    g = guard()
    with pytest.raises(ReadOnlyViolation):
        g.check(method, url, form)
    assert g.violations == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"checked": "26541125"},
        {"delete": "Delete Selected"},
        {"deleteAll": "Delete All"},
        {"pk": "1"},
        {"address": "x"},
    ],
)
def test_search_with_any_extra_field_is_refused(extra: dict[str, str]) -> None:
    refused("POST", BASE + SEARCH_PATH, {**good_search(), **extra})


@pytest.mark.parametrize("missing", sorted(SEARCH_FIELDS))
def test_search_missing_a_field_is_refused(missing: str) -> None:
    form = good_search()
    del form[missing]
    refused("POST", BASE + SEARCH_PATH, form)


@pytest.mark.parametrize(
    "changes",
    [
        {"query": "doDelete()"},
        {"query": ""},
        {"startDate": ""},
        {"endDate": ""},
        {"startDate": "2026-10-21"},
        {"startDate": "21/10/2026 00:00:00"},
        {"endDate": "2026-10-20 00:00:00"},  # before the start
        {"endDate": "2026-10-28 00:00:01"},  # more than 7 days
        {"queue": "javascript:doDelete()"},
    ],
)
def test_search_with_bad_values_is_refused(changes: dict[str, str]) -> None:
    refused("POST", BASE + SEARCH_PATH, {**good_search(), **changes})


@pytest.mark.parametrize(
    "form",
    [
        {"username": "u"},
        {"username": "u", "password": "p", "remember": "1"},
        {"username": "u", "password": "p", "checked": "1"},
    ],
)
def test_login_with_other_fields_is_refused(form: dict[str, str]) -> None:
    refused("POST", BASE + "/auth/login", form)


@pytest.mark.parametrize(
    "path",
    [
        "/ajax.html",
        "/realtime/realtime_calls.html",
        "/auth/logout",
        "/auth/forgot_password",
        "/my_account/voicemail_inbox.html",
        "/",
        "/index.html",
        "/recordings/",
        "/recordings/12345678/delete",
        "/Auth/login",
        "/auth/login/",
        "/auth//login",
        "/auth/./login",
        "/auth/../auth/login",
        "/auth/%6Cogin",
        "/auth\\login",
        "/auth/login?next=/",
        "/auth/login#x",
        "/auth/ login",
    ],
)
def test_paths_off_the_list_are_refused(path: str) -> None:
    refused("GET", BASE + path)


@pytest.mark.parametrize(
    "url",
    [
        "http://admin.ravon.net/auth/login",
        "https://evil.example/auth/login",
        "https://admin.ravon.net.evil.example/auth/login",
        "https://admin.ravon.net:8443/auth/login",
        "https://user:pw@admin.ravon.net/auth/login",
    ],
)
def test_other_hosts_schemes_ports_and_userinfo_are_refused(url: str) -> None:
    refused("GET", url)


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "get", "post"])
def test_other_methods_are_refused(method: str) -> None:
    refused(method, BASE + "/auth/login")


@pytest.mark.parametrize(
    "path", ["/recordings/99999999", "/recordings/026541125", "/recordings/1234"]
)
def test_unknown_or_malformed_recording_ids_are_refused(path: str) -> None:
    refused("GET", BASE + path)


def test_gets_and_audio_carry_no_form() -> None:
    refused("GET", BASE + "/auth/login", {"username": "u"})
    refused("GET", BASE + f"/recordings/{KNOWN_ID}", {"x": "1"})


def test_refusals_are_logged_without_form_values(caplog: pytest.LogCaptureFixture) -> None:
    g = guard()
    with caplog.at_level(logging.WARNING), pytest.raises(ReadOnlyViolation):
        g.check("POST", BASE + SEARCH_PATH, {**good_search(), "checked": "SECRET-ID-42"})
    assert "POST" in caplog.text
    assert SEARCH_PATH in caplog.text
    assert "SECRET-ID-42" not in caplog.text
    assert "tireProz" not in caplog.text


def test_http_base_is_allowed_only_for_local_test_servers() -> None:
    local = Guard("http://127.0.0.1:8765", is_known_recording=lambda _: False)
    local.check("GET", "http://127.0.0.1:8765/auth/login", None)
    with pytest.raises(ValueError, match="https"):
        Guard("http://admin.ravon.net", is_known_recording=lambda _: False)


# --- property test against a plain reference implementation --------------------------------

_DATE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def reference_allows(method: str, path: str, form: dict[str, str] | None) -> bool:
    """A deliberately simple restatement of the rules, written separately from the guard."""
    if method == "GET" and form is None and path in ("/auth/login", SEARCH_PATH):
        return True
    if method == "POST" and path == "/auth/login":
        return (
            form is not None
            and set(form) == {"username", "password"}
            and "dodelete" not in "".join(form.values()).lower()
        )
    if method == "POST" and path == SEARCH_PATH:
        if form is None or set(form) != SEARCH_FIELDS or form["query"] != "Find Calls":
            return False
        if not (_DATE.fullmatch(form["startDate"]) and _DATE.fullmatch(form["endDate"])):
            return False
        try:
            start = datetime.strptime(form["startDate"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(form["endDate"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        if "dodelete" in "".join(form.values()).lower() or "javascript:" in form["queue"].lower():
            return False
        return start <= end <= start + timedelta(days=7)
    if method == "GET" and form is None and path == f"/recordings/{KNOWN_ID}":
        return True
    return False


METHODS = st.sampled_from(["GET", "POST", "PUT", "DELETE", "get"])
PATHS = st.one_of(
    st.sampled_from(
        [
            "/auth/login",
            SEARCH_PATH,
            f"/recordings/{KNOWN_ID}",
            "/recordings/12345678",
            "/ajax.html",
            "/auth/logout",
            "/",
            "/auth/login/",
            "/AUTH/login",
        ]
    ),
    st.text(alphabet="/abcdeghilnortu.%_-", min_size=1, max_size=30).map(lambda s: "/" + s),
)
DATES = st.one_of(
    st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 31)).map(
        lambda d: d.strftime("%Y-%m-%d %H:%M:%S")
    ),
    st.sampled_from(["", "2026-10-21", "2026-13-01 00:00:00", "2026-10-21 25:00:00"]),
)
FIELD_NAMES = st.sampled_from(
    sorted(SEARCH_FIELDS | {"username", "password", "checked", "delete", "deleteAll", "pk"})
)


@st.composite
def forms(draw: st.DrawFn) -> dict[str, str] | None:
    kind = draw(st.sampled_from(["none", "search", "login", "random"]))
    if kind == "none":
        return None
    if kind == "search":
        form = search_form("tireProz-q", datetime(2026, 10, 1), datetime(2026, 10, 2))
        form["startDate"] = draw(DATES)
        form["endDate"] = draw(DATES)
        form["query"] = draw(st.sampled_from(["Find Calls", "Find Calls", "", "doDelete()"]))
        if draw(st.booleans()):
            form[draw(FIELD_NAMES)] = draw(st.text(max_size=8))
        if draw(st.booleans()):
            form.pop(draw(st.sampled_from(sorted(SEARCH_FIELDS))), None)
        return form
    if kind == "login":
        form = {"username": "u", "password": "p"}
        if draw(st.booleans()):
            form[draw(FIELD_NAMES)] = "x"
        return form
    return draw(st.dictionaries(FIELD_NAMES, st.text(max_size=8), max_size=4))


@settings(max_examples=3000, deadline=None)
@given(method=METHODS, path=PATHS, form=forms())
def test_guard_matches_the_reference(method: str, path: str, form: dict[str, str] | None) -> None:
    expected = reference_allows(method, path, form)
    try:
        guard().check(method, BASE + path, form)
        actual = True
    except ReadOnlyViolation:
        actual = False
    assert actual == expected, (method, path, form)
