"""A fake Ravon admin site for tests, modelled on the real pages' structure.

Used as an httpx transport handler (`httpx.MockTransport(fake.handle)`), so tests never touch
the network. Faults can be switched on to exercise the client's error handling. It holds only
invented data.
"""

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import parse_qsl

import httpx

LOGIN_PATH = "/auth/login"
SEARCH_PATH = "/realtime/manage_recorded_calls.html"
SEARCH_FIELDS = {"queue", "user", "conferencePK", "startDate", "endDate", "ani", "dnis", "query"}
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class FakeCall:
    id: int
    queue: str
    start_local: str
    minutes: float
    caller: str = "(405) 555-0100"
    answered_by: str = "SW Counter Sales"
    audio: bytes = b"ID3fake-mp3-bytes"


@dataclass
class FakeRavon:
    username: str = "admin@example.com"
    password: str = "correct-horse"
    queues: dict[str, str] = field(
        default_factory=lambda: {
            "tireProz-salescustserv": "Stillwater Sales/CS (x600)",
            "tireProz-SWafterHRS": "SWafterHRS (x599)",
            "tireProz-HDsales": "Hudson Sales/CS (x700)",
        }
    )
    calls: list[FakeCall] = field(default_factory=list[FakeCall])

    # Faults
    reject_logins: bool = False
    server_errors: int = 0  # the next N requests get a 500
    timeouts: int = 0  # the next N requests time out
    page_format_changed: bool = False
    truncate_audio: bool = False

    # Observations
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    logins: int = 0
    _sessions: set[str] = field(default_factory=set[str])

    def expire_sessions(self) -> None:
        self._sessions.clear()

    # --- dispatch --------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.timeouts > 0:
            self.timeouts -= 1
            raise httpx.ConnectTimeout("fake timeout", request=request)
        if self.server_errors > 0:
            self.server_errors -= 1
            return httpx.Response(500, text="Internal Server Error")

        path, method = request.url.path, request.method
        if path == LOGIN_PATH and method == "GET":
            return self._login_page(new_cookie=True)
        if path == LOGIN_PATH and method == "POST":
            return self._login(request)
        if not self._logged_in(request):
            return httpx.Response(302, headers={"Location": LOGIN_PATH})
        if path == SEARCH_PATH and method == "GET":
            return self._search_page([])
        if path == SEARCH_PATH and method == "POST":
            return self._search(request)
        if path.startswith("/recordings/") and method == "GET":
            return self._recording(path.removeprefix("/recordings/"))
        return httpx.Response(404, text="Not Found")

    # --- pages -----------------------------------------------------------------------------

    @staticmethod
    def _cookie(request: httpx.Request, name: str) -> str | None:
        for part in request.headers.get("cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return None

    def _logged_in(self, request: httpx.Request) -> bool:
        return self._cookie(request, "JSESSIONID") in self._sessions

    def _login_page(self, *, new_cookie: bool, error: str = "") -> httpx.Response:
        body = f"""<html><body><form method="post" action="/auth/login">
<div class="error">{escape(error)}</div>
<input name="username" type="email"/><input name="password" type="password"/>
<button type="submit">Log In</button></form></body></html>"""
        headers: list[tuple[str, str]] = []
        if new_cookie:
            headers.append(("Set-Cookie", f"JSESSIONID={secrets.token_hex(8)}; Path=/; HttpOnly"))
            headers.append(("Set-Cookie", f"session={secrets.token_hex(8)}; Path=/"))
        return httpx.Response(200, html=body, headers=headers)

    def _login(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        ok = (
            not self.reject_logins
            and form.get("username") == self.username
            and form.get("password") == self.password
        )
        if not ok:
            return self._login_page(new_cookie=False, error="Invalid username or password.")
        self.logins += 1
        session = self._cookie(request, "JSESSIONID") or secrets.token_hex(8)
        self._sessions.add(session)
        return httpx.Response(
            302, headers={"Location": "/", "Set-Cookie": f"JSESSIONID={session}; Path=/; HttpOnly"}
        )

    def _search(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        if set(form) != SEARCH_FIELDS:
            # The real page would act on extra fields (it holds delete controls); fail loudly.
            raise AssertionError(f"search sent unexpected fields: {sorted(form)}")
        start = datetime.strptime(form["startDate"], DATE_FORMAT)
        end = datetime.strptime(form["endDate"], DATE_FORMAT)
        rows = [
            c
            for c in self.calls
            if (not form["queue"] or c.queue == form["queue"])
            and start <= datetime.strptime(c.start_local, DATE_FORMAT) <= end
        ]
        return self._search_page(rows)

    def _search_page(self, rows: list[FakeCall]) -> httpx.Response:
        options = '<option value="">All Queues</option>' + "".join(
            f'<option value="{escape(v)}">{escape(label)}</option>'
            for v, label in self.queues.items()
        )
        data = [
            {
                "select": (
                    f"<input type='checkbox' class='selectOne' value='{c.id}' name='checked' />"
                ),
                "Start Time": c.start_local,
                "Minutes": f"{c.minutes:.2f}",
                "From": c.caller,
                "To": c.answered_by,
                "tools": "<img class='playRecording' src='/graphics/play.png' />",
            }
            for c in rows
        ]
        table = (
            "<p>Recordings are listed in a table.</p>"
            if self.page_format_changed
            else f'$("#recordingTable").DataTable({{ data: {json.dumps(data)}, pageLength: 25 }});'
        )
        body = f"""<html><body>
<form method="post" action="{SEARCH_PATH}">
<select name="queue">{options}</select>
<select name="user"><option value="">All Users</option></select>
<select name="conferencePK"><option value="">All</option></select>
<input name="startDate"/><input name="endDate"/><input name="ani"/><input name="dnis"/>
<button type="submit" name="query">Find Calls</button>
</form>
<form method="post"><input type="submit" name="delete" value="Delete Selected"
 onclick="return doDelete();"/><input type="submit" name="deleteAll" value="Delete All"/></form>
<table id="recordingTable"></table>
<script>{table}</script>
</body></html>"""
        return httpx.Response(200, html=body)

    def _recording(self, raw_id: str) -> httpx.Response:
        call = next((c for c in self.calls if str(c.id) == raw_id), None)
        if call is None:
            return httpx.Response(404, text="Not Found")
        content = call.audio[: len(call.audio) // 2] if self.truncate_audio else call.audio
        headers = {"Content-Type": "audio/mpeg", "Content-Length": str(len(call.audio))}
        return httpx.Response(200, content=content, headers=headers)
