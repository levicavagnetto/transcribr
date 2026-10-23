"""The only way the app talks to Ravon: a paced, guarded httpx client.

Every request goes through GuardedTransport, so code that builds a request by hand still
cannot get past the allow list. Redirects are never followed; a redirect to the login page is
read as an expired session.
"""

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import parse_qsl

import httpx

from transcribr.ravon.guard import (
    LOGIN_PATH,
    MAX_SEARCH_SPAN,
    SEARCH_PATH,
    Guard,
    search_form,
)
from transcribr.ravon.parse import Queue, Recording, parse_queues, parse_recordings

log = logging.getLogger(__name__)

MIN_REQUEST_INTERVAL = 1.0
FAILURES_BEFORE_BACKOFF = 5
FIRST_BACKOFF_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 600.0
REQUEST_TIMEOUT = 20.0
HTTP_OK = 200
HTTP_SERVER_ERROR = 500

LoginState = Literal["unknown", "ok", "rejected"]


class RavonError(Exception):
    pass


class RavonUnavailable(RavonError):
    """Ravon did not answer usefully (network error, timeout, 5xx, or backing off)."""


class LoginRejected(RavonError):
    """Ravon refused the credentials. No more attempts until they change or a retry is asked."""


class NoCredentials(RavonError):
    """No Ravon username and password are configured."""


class AudioIncomplete(RavonError):
    """The recording download was shorter than Ravon said it would be."""


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _never_known(_recording_id: int) -> bool:
    return False


def credential_fingerprint(username: str, password: str) -> str:
    """A hash to recognise "the same credentials as last time" without storing them."""
    return hashlib.sha256(f"{username}\0{password}".encode()).hexdigest()


def _form_of(request: httpx.Request) -> dict[str, str] | None:
    body = request.content
    if not body:
        return None
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/x-www-form-urlencoded"):
        return {"<unexpected body>": content_type}
    return dict(parse_qsl(body.decode(), keep_blank_values=True))


class GuardedTransport(httpx.BaseTransport):
    def __init__(self, guard: Guard, inner: httpx.BaseTransport) -> None:
        self._guard = guard
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._guard.check(request.method, str(request.url), _form_of(request))
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


class RavonClient:
    def __init__(  # noqa: PLR0913 - explicit dependencies keep this testable
        self,
        base_url: str,
        username: str | None,
        password: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
        is_known_recording: Callable[[int], bool] | None = None,
        rejected_fingerprint: str | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL,
    ) -> None:
        self._username = username
        self._password = password
        self._clock = clock or SystemClock()
        self._min_interval = min_interval
        self._known: set[int] = set()
        external = is_known_recording or _never_known
        self.guard = Guard(
            base_url, is_known_recording=lambda rid: rid in self._known or external(rid)
        )
        self.http = httpx.Client(
            base_url=base_url,
            transport=GuardedTransport(self.guard, transport or httpx.HTTPTransport()),
            follow_redirects=False,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Transcribr (read-only)"},
        )
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self.consecutive_failures = 0
        self.backoff_seconds = 0.0
        self._blocked_until = 0.0
        self.login_state: LoginState = "unknown"
        self.rejected_fingerprint = rejected_fingerprint
        fingerprint = self._fingerprint()
        if fingerprint is not None and fingerprint == rejected_fingerprint:
            self.login_state = "rejected"

    # --- public operations ---------------------------------------------------------------

    def queues(self) -> list[Queue]:
        return parse_queues(self._authed("GET", SEARCH_PATH).text)

    def search(self, queue: str, start: datetime, end: datetime) -> list[Recording]:
        """All recordings that started in [start, end], split into searches of at most 7 days."""
        found: dict[int, Recording] = {}
        window_start = start
        while True:
            window_end = min(end, window_start + MAX_SEARCH_SPAN)
            page = self._authed("POST", SEARCH_PATH, search_form(queue, window_start, window_end))
            for recording in parse_recordings(page.text):
                found.setdefault(recording.id, recording)
            if window_end >= end:
                break
            window_start = window_end
        self._known.update(found)
        return sorted(found.values(), key=lambda r: (r.start_local, r.id))

    def download(self, recording_id: int) -> bytes:
        """The recording's MP3 bytes, in memory only."""
        response = self._authed("GET", f"/recordings/{recording_id}")
        if response.status_code != HTTP_OK:
            raise RavonError(f"recording {recording_id}: HTTP {response.status_code}")
        declared = response.headers.get("content-length")
        if declared is None or int(declared) != len(response.content):
            raise AudioIncomplete(
                f"recording {recording_id}: got {len(response.content)} bytes, expected {declared}"
            )
        return response.content

    def retry_login(self) -> None:
        """Operator action: allow one more login attempt with the current credentials."""
        self.login_state = "unknown"
        self.rejected_fingerprint = None

    def close(self) -> None:
        self.http.close()

    # --- login -----------------------------------------------------------------------------

    def _fingerprint(self) -> str | None:
        if not self._username or not self._password:
            return None
        return credential_fingerprint(self._username, self._password)

    def _login(self) -> None:
        fingerprint = self._fingerprint()
        if fingerprint is None or self._username is None or self._password is None:
            raise NoCredentials("RAVON_USERNAME and RAVON_PASSWORD are not set")
        if self.login_state == "rejected":
            raise LoginRejected("Ravon rejected these credentials; waiting for a change or retry")
        self.http.cookies.clear()
        self._send("GET", LOGIN_PATH)
        response = self._send(
            "POST", LOGIN_PATH, {"username": self._username, "password": self._password}
        )
        location = response.headers.get("location", "")
        if response.is_redirect and LOGIN_PATH not in location:
            self.login_state = "ok"
            log.info("logged in to Ravon")
            return
        self.login_state = "rejected"
        self.rejected_fingerprint = fingerprint
        log.error("Ravon rejected the login; no more attempts until credentials change or retry")
        raise LoginRejected("Ravon rejected the username or password")

    @staticmethod
    def _is_login_redirect(response: httpx.Response) -> bool:
        return response.is_redirect and LOGIN_PATH in response.headers.get("location", "")

    def _authed(self, method: str, path: str, form: dict[str, str] | None = None) -> httpx.Response:
        if self.login_state != "ok":
            self._login()
        response = self._send(method, path, form)
        if self._is_login_redirect(response):
            log.info("Ravon session expired; logging in again")
            self.login_state = "unknown"
            self._login()
            response = self._send(method, path, form)
            if self._is_login_redirect(response):
                raise RavonError("Ravon did not accept the new session")
        return response

    # --- sending -----------------------------------------------------------------------------

    def _send(self, method: str, path: str, form: dict[str, str] | None = None) -> httpx.Response:
        with self._lock:
            now = self._clock.monotonic()
            if now < self._blocked_until:
                raise RavonUnavailable(
                    f"backing off for {self._blocked_until - now:.0f} s after repeated failures"
                )
            if self._last_request is not None:
                wait = self._last_request + self._min_interval - now
                if wait > 0:
                    self._clock.sleep(wait)
            self._last_request = self._clock.monotonic()
            try:
                response = self.http.request(method, path, data=form)
            except httpx.TimeoutException as error:
                self._failed()
                raise RavonUnavailable(f"Ravon timed out: {type(error).__name__}") from None
            except httpx.TransportError as error:
                self._failed()
                raise RavonUnavailable(f"could not reach Ravon: {type(error).__name__}") from None
            if response.status_code >= HTTP_SERVER_ERROR:
                self._failed()
                raise RavonUnavailable(f"Ravon answered HTTP {response.status_code}")
            self.consecutive_failures = 0
            self.backoff_seconds = 0.0
            return response

    def _failed(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= FAILURES_BEFORE_BACKOFF:
            steps = self.consecutive_failures - FAILURES_BEFORE_BACKOFF
            self.backoff_seconds = min(MAX_BACKOFF_SECONDS, FIRST_BACKOFF_SECONDS * 2**steps)
            self._blocked_until = self._clock.monotonic() + self.backoff_seconds
            log.warning(
                "Ravon failed %d times in a row; pausing %.0f s",
                self.consecutive_failures,
                self.backoff_seconds,
            )
