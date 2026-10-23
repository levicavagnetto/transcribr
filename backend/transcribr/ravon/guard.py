"""The read-only allow list every request to Ravon must pass before it is sent.

Ravon is a live system the shop depends on, and its recordings page also holds delete
controls. Anything not explicitly allowed here is refused, and refusals are logged with the
method and path only, never form values.
"""

import logging
import re
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from urllib.parse import SplitResult, urlsplit

log = logging.getLogger(__name__)

LOGIN_PATH = "/auth/login"
SEARCH_PATH = "/realtime/manage_recorded_calls.html"
SEARCH_FIELDS = frozenset(
    {"queue", "user", "conferencePK", "startDate", "endDate", "ani", "dnis", "query"}
)
LOGIN_FIELDS = frozenset({"username", "password"})
SEARCH_BUTTON = "Find Calls"
MAX_SEARCH_SPAN = timedelta(days=7)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_DATE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_RECORDING = re.compile(r"/recordings/([1-9]\d{4,11})")
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class ReadOnlyViolation(Exception):
    """A request that is not on the allow list. It was not sent."""


def search_form(queue: str, start: datetime, end: datetime) -> dict[str, str]:
    """The exact eight fields of a recordings search, and nothing else."""
    return {
        "queue": queue,
        "user": "",
        "conferencePK": "",
        "startDate": start.strftime(DATE_FORMAT),
        "endDate": end.strftime(DATE_FORMAT),
        "ani": "",
        "dnis": "",
        "query": SEARCH_BUTTON,
    }


def _parse_date(value: str) -> datetime | None:
    if not _DATE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None


class Guard:
    def __init__(self, base_url: str, *, is_known_recording: Callable[[int], bool]) -> None:
        base = urlsplit(base_url)
        local = base.hostname in _LOCAL_HOSTS
        if base.scheme != "https" and not (base.scheme == "http" and local):
            raise ValueError("Ravon must be reached over https (http only for local test servers)")
        self._scheme = base.scheme
        self._netloc = base.netloc
        self._is_known_recording = is_known_recording
        self._lock = threading.Lock()
        self._violations = 0

    @property
    def violations(self) -> int:
        return self._violations

    def check(self, method: str, url: str, form: Mapping[str, str] | None) -> None:
        """Raise ReadOnlyViolation unless this exact request is allowed."""
        parts = urlsplit(url)
        reason = self._refusal(method, parts, "#" in url or "?" in url, form)
        if reason is not None:
            with self._lock:
                self._violations += 1
            log.warning("refused Ravon request %s %s: %s", method, parts.path, reason)
            raise ReadOnlyViolation(f"{method} {parts.path}: {reason}")

    def _refusal(  # noqa: PLR0911 - one early return per rule reads best here
        self,
        method: str,
        parts: SplitResult,
        has_query_or_fragment: bool,
        form: Mapping[str, str] | None,
    ) -> str | None:
        if parts.scheme != self._scheme or parts.netloc != self._netloc:
            return "not the Ravon address"
        if has_query_or_fragment:
            return "query strings and fragments are not allowed"
        if method not in ("GET", "POST"):
            return "method not allowed"
        if form is not None and any("dodelete" in v.lower() for v in form.values()):
            return "form value mentions a delete action"

        path = parts.path
        if method == "GET":
            if form is not None:
                return "GET requests carry no form"
            if path in (LOGIN_PATH, SEARCH_PATH):
                return None
            match = _RECORDING.fullmatch(path)
            if match and self._is_known_recording(int(match.group(1))):
                return None
            return "path not on the allow list"

        if form is None:
            return "POST without a form"
        if path == LOGIN_PATH:
            if frozenset(form) == LOGIN_FIELDS:
                return None
            return "login takes exactly username and password"
        if path == SEARCH_PATH:
            return self._search_refusal(form)
        return "path not on the allow list"

    @staticmethod
    def _search_refusal(form: Mapping[str, str]) -> str | None:  # noqa: PLR0911 - one per rule
        if frozenset(form) != SEARCH_FIELDS:
            return "search takes exactly the eight search fields"
        if form["query"] != SEARCH_BUTTON:
            return "search button value is wrong"
        if "javascript:" in form["queue"].lower():
            return "queue value is not a queue name"
        start = _parse_date(form["startDate"])
        end = _parse_date(form["endDate"])
        if start is None or end is None:
            return "search needs a start and end date-time"
        if end < start:
            return "search ends before it starts"
        if end - start > MAX_SEARCH_SPAN:
            return "search spans more than 7 days"
        return None
