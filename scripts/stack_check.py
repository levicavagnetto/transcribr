"""Run the real container stack against the fake Ravon, with the worker cut off from the internet.

    uv run --directory backend ../scripts/stack_check.py [smoke|resilience|backlog|verify] [--keep]

Each mode builds the images, starts web + worker + fake Ravon (backend/tests/stack) on a fresh
volume, creates the admin from the setup code in the web log and chooses a queue, then:

  smoke       (default, task 10.1) a new call is auto-transcribed; a call that ends while the
              worker is down is listed as Not transcribed and only transcribed on request; the
              home page counts match the database.
  resilience  (task 10.2) the worker is killed mid-call, the containers are recreated, and the
              image is updated to one with a no-op migration; no call is lost, duplicated or
              stuck, and the data persists. Saves a snapshot for `verify`.
  backlog     (task 10.4) with 50 calls waiting, the home page and status API answer in < 2 s.
  verify      check an already running stack (after `resilience --keep` and a Docker restart)
              against the saved snapshot.

The stack and its volume are removed afterwards unless --keep is given. Needs Docker; exits
non-zero on the first failed step.
"""

import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
STACK = ROOT / "backend" / "tests" / "stack"
PROJECT = "transcribr-stack"
COMPOSE = [
    "docker", "compose", "-p", PROJECT,
    "-f", str(ROOT / "compose.yaml"),
    "-f", str(STACK / "compose.offline.yaml"),
    "--env-file", str(STACK / "stack.env"),
]  # fmt: skip
BASE_URL = "http://127.0.0.1:18000"
WRITE = {"X-Transcribr": "1"}
QUEUE = "tireProz-salescustserv"
UPDATE_IMAGE = "transcribr:noop-update"
SNAPSHOT = Path(tempfile.gettempdir()) / "transcribr-stack-snapshot.json"
# Uptime spans (design D4): a gap over 3 minutes starts a new span, and a call counts as
# "while running" within 2 minutes of a span. So a missed call needs about 5 minutes down.
DOWN_BEFORE_CALL = 150
DOWN_AFTER_CALL = 150
WEB_LATENCY_LIMIT = 2.0

# Each mode uses its own block of recording IDs (Ravon's are 5-12 digits).
AUTO_CALL, MISSED_CALL, CRASH_CALL, AFTER_UPDATE_CALL = 90001001, 90001002, 90001003, 90001004
CHECK_NOW_CALL = 90001005
AUTO_CALLER = "(405) 555-0142"
FIXTURE_BYTES = (ROOT / "backend/tests/fixtures/audio/two-voices.mp3").stat().st_size
CHECK_NOW_LIMIT = 30  # seconds; the schedule is 30 minutes during that step
BACKLOG_FIRST, BACKLOG_COUNT = 90002001, 50


class StepFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n== {name} ==", flush=True)


def wait_until(what: str, check: Callable[[], bool], timeout: float, every: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise StepFailed(f"timed out after {timeout:.0f} s waiting for {what}")
        time.sleep(every)


class Stack:
    def __init__(self) -> None:
        self.env = dict(os.environ)
        self.web = httpx.Client(base_url=BASE_URL, timeout=10)

    # --- docker ------------------------------------------------------------------------------

    def compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(  # noqa: S603 - fixed docker command
            [*COMPOSE, *args], cwd=ROOT, env=self.env, capture_output=True, text=True, check=False
        )
        if check and result.returncode != 0:
            raise StepFailed(f"docker compose {' '.join(args)} failed:\n{result.stderr[-3000:]}")
        return result

    def db(self, sql: str) -> list[list[Any]]:
        """Run a read-only query in the web container and return the rows."""
        code = (
            "import json, sqlite3, sys;"
            "c = sqlite3.connect('file:/data/transcribr.db?mode=ro', uri=True);"
            "print(json.dumps(c.execute(sys.argv[1]).fetchall()))"
        )
        out = self.compose("exec", "-T", "web", "python", "-c", code, sql).stdout
        rows: list[list[Any]] = json.loads(out)
        return rows

    def one(self, sql: str) -> Any:
        rows = self.db(sql)
        return rows[0][0] if rows else None

    def add_calls(
        self, first: int, *, ends_in: float, count: int = 1, caller: str = "(405) 555-0100"
    ) -> None:
        self.compose(
            "exec", "-T", "fake-ravon", "python", "-m", "tests.fake_ravon.serve",
            "add-call", str(first), "--queue", QUEUE, "--audio", "two-voices",
            f"--ended-seconds-ago={-ends_in}", "--count", str(count), "--caller", caller,
        )  # fmt: skip

    def listen_from_worker_namespace(self, call_id: int) -> tuple[int, str, int]:
        """Fetch a recording through a second web process in the worker's container.

        The stack's own web service can't reach the fake Ravon (only the worker shares its
        loopback), so this runs the same image's web service where it can, on port 8001.
        """
        self.compose("exec", "-d", "-e", "TRANSCRIBR_PORT=8001", "worker", "transcribr", "web")
        fetch = (
            "import sys, time, urllib.request\n"
            "base = 'http://127.0.0.1:8001/api/v1'\n"
            "for _ in range(60):\n"
            "    try:\n"
            "        urllib.request.urlopen(base + '/health', timeout=2)\n"
            "        break\n"
            "    except Exception:\n"
            "        time.sleep(1)\n"
            "r = urllib.request.urlopen(base + '/calls/' + sys.argv[1] + '/audio', timeout=90)\n"
            "print(r.status, r.headers['content-type'], len(r.read()))\n"
        )
        stop = (
            "import os, signal\n"
            "for pid in filter(str.isdigit, os.listdir('/proc')):\n"
            "    try:\n"
            "        cmd = open('/proc/' + pid + '/cmdline', 'rb').read()\n"
            "    except OSError:\n"
            "        continue\n"
            "    if cmd.endswith(b'transcribr\\x00web\\x00'):\n"
            "        os.kill(int(pid), signal.SIGTERM)\n"
        )
        try:
            out = self.compose("exec", "-T", "worker", "python", "-c", fetch, str(call_id)).stdout
        finally:
            self.compose("exec", "-T", "worker", "python", "-c", stop, check=False)
        status, content_type, size = shlex.split(out.strip().splitlines()[-1])
        return int(status), content_type, int(size)

    def restarts(self, service: str) -> int:
        out = subprocess.run(  # noqa: S603
            ["docker", "inspect", "-f", "{{.RestartCount}}", f"{PROJECT}-{service}-1"],  # noqa: S607
            capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
        return int(out.strip())

    # --- web ---------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        status: dict[str, Any] = self.web.get("/api/v1/status").json()
        return status

    def state_of(self, rid: int) -> str | None:
        state: str | None = self.one(f"SELECT state FROM calls WHERE id = {rid}")  # noqa: S608
        return state

    def wait_for_state(self, rid: int, state: str, timeout: float = 300) -> None:
        def reached() -> bool:
            current = self.state_of(rid)
            if current == "failed":
                reason = self.one(f"SELECT failure_reason FROM calls WHERE id = {rid}")  # noqa: S608
                raise StepFailed(f"call {rid} failed: {reason}")
            return current == state

        wait_until(f"call {rid} to be {state}", reached, timeout, every=2)

    def wait_for_poll(self, timeout: float = 150) -> None:
        before = self.status()["last_poll_ok"]
        wait_until(
            "the worker's next poll", lambda: self.status()["last_poll_ok"] != before, timeout
        )

    def wait_healthy(self, timeout: float = 240) -> None:
        def healthy() -> bool:
            out = self.compose("ps", "--format", "{{.Service}} {{.Health}}", check=False).stdout
            health = dict(line.split(" ", 1) for line in out.strip().splitlines() if " " in line)
            return health.get("web") == "healthy" and health.get("worker") == "healthy"

        wait_until("web and worker to be healthy", healthy, timeout)

    # --- shared steps ------------------------------------------------------------------------

    def start_fresh(self) -> None:
        step("build the runtime and test images")
        self.compose("build")
        step("start web, worker and the fake Ravon on a fresh volume")
        self.compose("down", "--volumes", check=False)
        self.compose("up", "-d", "--wait", "--wait-timeout", "300")
        print(self.compose("ps", "--format", "{{.Service}}: {{.Status}}").stdout.strip())

        step("check the worker can't reach the internet")
        probe = self.compose(
            "exec", "-T", "worker", "python", "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)",
            check=False,
        )  # fmt: skip
        if probe.returncode == 0:
            raise StepFailed("the worker reached 1.1.1.1; the offline overlay isn't in effect")
        print("no route out, as intended")

        step("create the admin from the logged setup code and choose a queue")
        response = self.web.post(
            "/api/v1/auth/setup",
            headers=WRITE,
            json={"code": self.setup_code(), "username": "admin", "password": "stack passphrase"},
        )
        if response.status_code != 200:
            raise StepFailed(f"admin setup: HTTP {response.status_code} {response.text}")
        response = self.web.put(
            "/api/v1/admin/settings",
            headers=WRITE,
            json={
                "store_queues": [QUEUE],
                "poll_interval_minutes": 1,
                "time_zone": "America/Chicago",
            },
        )
        if response.status_code != 200:
            raise StepFailed(f"settings: HTTP {response.status_code} {response.text}")
        # The worker follows a newly chosen queue from its next poll; calls that end before
        # then count as missed, so the checks below only add calls after that poll.
        self.wait_for_poll()

    def setup_code(self) -> str:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            logs = self.compose("logs", "web").stdout
            match = re.search(r"Admin setup code: ([A-Z0-9-]+)", logs)
            if match:
                return match.group(1)
            time.sleep(2)
        raise StepFailed("no admin setup code in the web log")

    def snapshot(self) -> dict[str, Any]:
        """What must survive restarts: every call with its state, and the transcript rows."""
        return {
            "calls": {str(rid): state for rid, state in self.db("SELECT id, state FROM calls")},
            "segments": self.one("SELECT count(*) FROM segments"),
            "admin": self.one("SELECT username FROM admin"),
            "store_queues": self.one("SELECT value FROM settings WHERE key = 'store_queues'"),
        }

    def check_invariants(self) -> None:
        """No call stuck, no work left claimed, every transcript whole and stored once."""
        step("check nothing is stuck, duplicated or half-written")
        stuck = self.db("SELECT id, state FROM calls WHERE state IN ('processing', 'failed')")
        claimed = self.db("SELECT id, call_id FROM jobs WHERE claimed_at IS NOT NULL")
        missing = self.db(
            "SELECT id FROM calls WHERE state = 'transcribed' AND (id NOT IN"
            " (SELECT call_id FROM transcripts) OR id NOT IN (SELECT call_id FROM segments))"
        )
        doubled = self.db(
            "SELECT call_id, idx, count(*) FROM segments GROUP BY call_id, idx HAVING count(*) > 1"
        )
        orphans = self.db(
            "SELECT call_id FROM jobs WHERE type = 'transcribe' AND call_id NOT IN"
            " (SELECT id FROM calls WHERE state = 'waiting')"
        )
        problems = {
            "stuck or failed calls": stuck,
            "claimed jobs": claimed,
            "transcribed calls without a transcript": missing,
            "duplicated transcript lines": doubled,
            "jobs for calls that aren't waiting": orphans,
        }
        found = {name: rows for name, rows in problems.items() if rows}
        if found:
            raise StepFailed(f"invariants broken: {found}")
        print("none")


# --- modes -----------------------------------------------------------------------------------


def smoke(stack: Stack) -> None:
    step("the admin adds a person before any call is transcribed")
    nolan = stack.web.post(
        "/api/v1/admin/profiles",
        headers=WRITE,
        json={"display_name": "Nolan", "variants": ["Nolan"]},
    )
    if nolan.status_code != 200:
        raise StepFailed(f"create profile: HTTP {nolan.status_code} {nolan.text}")
    person: int = nolan.json()["id"]
    print(f"profile {person}: Nolan")

    step("a call that ends while the worker runs is transcribed automatically")
    stack.add_calls(AUTO_CALL, ends_in=20, caller=AUTO_CALLER)
    stack.wait_for_state(AUTO_CALL, "transcribed")
    if stack.one(f"SELECT auto_queued FROM calls WHERE id = {AUTO_CALL}") != 1:  # noqa: S608
        raise StepFailed("the call was transcribed but not marked as auto-queued")
    print("transcribed, auto-queued")

    step(f"stop the worker; a call ends while it is down ({DOWN_BEFORE_CALL + DOWN_AFTER_CALL} s)")
    stack.compose("stop", "worker")
    time.sleep(DOWN_BEFORE_CALL)
    stack.add_calls(MISSED_CALL, ends_in=5)
    time.sleep(DOWN_AFTER_CALL)
    stack.compose("start", "worker")

    step("the missed call is listed as Not transcribed, and stays that way")
    wait_until("the missed call to be listed", lambda: stack.state_of(MISSED_CALL) is not None, 240)
    stack.wait_for_poll()
    if stack.state_of(MISSED_CALL) != "not_transcribed":
        raise StepFailed(f"missed call is {stack.state_of(MISSED_CALL)}, not not_transcribed")
    if stack.status()["waiting"]:
        raise StepFailed("something was queued without a request (auto-backfill)")
    print("not_transcribed after the catch-up and one more poll")

    step("the Transcribe request transcribes it")
    response = stack.web.post(f"/api/v1/calls/{MISSED_CALL}/transcribe", headers=WRITE)
    if response.json() != {"queued": True, "state": "waiting"}:
        raise StepFailed(f"transcribe request: {response.status_code} {response.text}")
    stack.wait_for_state(MISSED_CALL, "transcribed")
    print("transcribed")

    find_and_read_a_call(stack)
    attribution(stack, person)

    step("the home page loads and its counts match the database")
    home = stack.web.get("/")
    if home.status_code != 200 or "text/html" not in home.headers.get("content-type", ""):
        raise StepFailed(f"home page: HTTP {home.status_code} {home.headers.get('content-type')}")
    status = stack.status()
    listed, transcribed, waiting = stack.db(
        "SELECT count(*), sum(state = 'transcribed'), sum(state IN ('waiting', 'processing'))"
        " FROM calls"
    )[0]
    shown = (status["listed_today"], status["transcribed_today"], status["waiting"])
    if shown != (listed, transcribed, waiting) or shown != (2, 2, 0):
        raise StepFailed(f"home page shows {shown}, database has {(listed, transcribed, waiting)}")
    if status["failed_last_24h"] or status["ravon_state"] != "ok" or status["guard_violations"]:
        raise StepFailed(f"unexpected status: {status}")
    print(f"listed {shown[0]}, transcribed {shown[1]}, waiting {shown[2]}, failed 0, Ravon ok")

    check_ravon_now(stack)
    stack.check_invariants()


def find_and_read_a_call(stack: Stack) -> None:
    """The call browser's API on the real stack (add-call-browser 3.1)."""
    step("find the call by a phrase from its transcript, and by its number")
    transcript = stack.web.get(f"/api/v1/calls/{AUTO_CALL}/transcript").json()
    words = next(
        found
        for segment in transcript["segments"]
        if len(found := re.findall(r"\w+", segment["text"])) >= 2
    )
    phrase = " ".join(words[:2])
    hits = stack.web.get("/api/v1/calls", params={"q": phrase}).json()["calls"]
    match = next((c for c in hits if c["id"] == AUTO_CALL), None)
    if match is None or not any(p["hit"] for p in match["passage"]["parts"]):
        raise StepFailed(f"searching {phrase!r} didn't find the call with a highlight: {hits}")
    by_number = stack.web.get("/api/v1/calls", params={"number": "555-0142"}).json()["calls"]
    if [c["id"] for c in by_number] != [AUTO_CALL]:
        raise StepFailed(f"number search found {[c['id'] for c in by_number]}")
    print(f"{phrase!r} found it at {match['passage']['at_s']:.0f} s; 555-0142 found it alone")

    step("the call page's details and timestamped transcript, without speakers")
    detail = stack.web.get(f"/api/v1/calls/{AUTO_CALL}").json()
    if (detail["state"], detail["auto_queued"], detail["has_transcript"]) != (
        "transcribed",
        True,
        True,
    ):
        raise StepFailed(f"call detail: {detail}")
    segments = transcript["segments"]
    if (
        not segments
        or "speakers" in transcript
        or any("speaker" in s or "voice" in s for s in segments)
    ):
        raise StepFailed(f"transcript: {transcript}")
    print(f"{len(segments)} lines, no speaker labels and no voice data")

    step("Copy for ChatGPT gets the prompt, details and lines it formats")
    prompt = stack.web.get("/api/v1/research-prompt").json()["prompt"]
    lines = [
        f"[{int(s['start_s']) // 60}:{int(s['start_s']) % 60:02d}] {s['text']}" for s in segments
    ]
    text = f"{prompt}\n\nCall: {detail['start_local']}\n\n" + "\n".join(lines)
    pattern = r"Below is a phone call.+\n\nCall: .+\n\n(\[\d+:\d\d\] .+\n?)+"
    if not re.fullmatch(pattern, text, flags=re.DOTALL):
        raise StepFailed(f"the copy text doesn't have the expected shape:\n{text}")
    print("prompt, call line and [m:ss] lines all present")

    step("Listen plays the recording through the server")
    status, content_type, size = stack.listen_from_worker_namespace(AUTO_CALL)
    if (status, content_type, size) != (200, "audio/mpeg", FIXTURE_BYTES):
        raise StepFailed(f"Listen answered {status} {content_type} with {size} bytes")
    print(f"200 audio/mpeg, {size} bytes, as Ravon sent it")


def people_on(stack: Stack, rid: int) -> list[tuple[str, str]]:
    attributions = stack.web.get(f"/api/v1/calls/{rid}").json()["attributions"]
    return [(a["status"], a["method"]) for a in attributions]


def attribution(stack: Stack, person: int) -> None:
    """Call attribution on the real stack (add-call-attribution 7.1)."""
    step("the name in the greeting makes each call a Maybe for that person")
    for rid in (AUTO_CALL, MISSED_CALL):
        if people_on(stack, rid) != [("maybe", "name")]:
            raise StepFailed(f"call {rid} attributions: {people_on(stack, rid)}")
    listed = stack.web.get("/api/v1/calls", params={"person": person, "maybe": "true"}).json()
    if sorted(c["id"] for c in listed["calls"]) != sorted((AUTO_CALL, MISSED_CALL)):
        raise StepFailed(f"the Maybe filter shows {[c['id'] for c in listed['calls']]}")
    print("both calls are Maybe by name, and both show under the person's Maybe filter")

    step("Confirm makes one Confident; Not removes the person from the other")
    confirm = stack.web.post(
        f"/api/v1/calls/{AUTO_CALL}/attributions/{person}/confirm", headers=WRITE
    )
    reject = stack.web.delete(f"/api/v1/calls/{MISSED_CALL}/attributions/{person}", headers=WRITE)
    if confirm.status_code != 200 or reject.status_code != 200:
        raise StepFailed(
            f"confirm {confirm.status_code} {confirm.text};"
            f" reject {reject.status_code} {reject.text}"
        )
    print("confirmed and rejected")

    step("changing the person's spellings rematches without undoing either decision")
    edit = stack.web.put(
        f"/api/v1/admin/profiles/{person}",
        headers=WRITE,
        json={"display_name": "Nolan", "variants": ["Nolan", "Nolen"]},
    )
    if edit.status_code != 200:
        raise StepFailed(f"edit profile: HTTP {edit.status_code} {edit.text}")
    wait_until(
        "the rematch to finish",
        lambda: stack.one("SELECT count(*) FROM jobs WHERE type = 'rematch'") == 0,
        120,
    )
    if (people_on(stack, AUTO_CALL), people_on(stack, MISSED_CALL)) != (
        [("confident", "manual")],
        [],
    ):
        raise StepFailed(
            f"after the rematch: {people_on(stack, AUTO_CALL)} and {people_on(stack, MISSED_CALL)}"
        )
    if stack.one(f"SELECT status FROM attributions WHERE call_id = {MISSED_CALL}") != "rejected":  # noqa: S608
        raise StepFailed("the rejection was not kept")
    print("still Confident and still rejected after the rematch")


def check_ravon_now(stack: Stack) -> None:
    step(
        f"Check Ravon now lists a new call within {CHECK_NOW_LIMIT} s, with the schedule at 30 min"
    )
    response = stack.web.put(
        "/api/v1/admin/settings", headers=WRITE, json={"poll_interval_minutes": 30}
    )
    if response.status_code != 200:
        raise StepFailed(f"settings: HTTP {response.status_code} {response.text}")
    time.sleep(16)  # past the 15-second cooldown after the last check
    stack.add_calls(CHECK_NOW_CALL, ends_in=-2)  # ended 2 s ago
    started = time.monotonic()
    response = stack.web.post("/api/v1/check-ravon", headers=WRITE)
    if response.status_code != 200:
        raise StepFailed(f"check-ravon: HTTP {response.status_code} {response.text}")
    wait_until(
        "Check Ravon now to list the call",
        lambda: stack.state_of(CHECK_NOW_CALL) is not None,
        CHECK_NOW_LIMIT,
        every=1,
    )
    print(f"listed after {time.monotonic() - started:.1f} s")
    stack.wait_for_state(CHECK_NOW_CALL, "transcribed")


def resilience(stack: Stack) -> None:
    step("kill the worker process while it transcribes a call")
    restarts_before = stack.restarts("worker")
    stack.add_calls(CRASH_CALL, ends_in=20)
    stack.wait_for_state(CRASH_CALL, "processing", timeout=240)
    stack.compose(
        "exec", "-T", "worker", "sh", "-c", "kill -9 $(cat /proc/1/task/1/children)", check=False
    )
    wait_until(
        "Docker to restart the worker", lambda: stack.restarts("worker") > restarts_before, 60
    )
    stack.wait_for_state(CRASH_CALL, "transcribed")
    print(f"restarted by Docker ({stack.restarts('worker')} restart), then transcribed")
    stack.check_invariants()
    before = stack.snapshot()

    step("remove and recreate the containers (the volume stays)")
    stack.compose("down")
    stack.compose("up", "-d", "--wait", "--wait-timeout", "300")
    if stack.snapshot() != before:
        raise StepFailed(f"data changed across recreation:\n{before}\n{stack.snapshot()}")
    print(f"same data: {len(before['calls'])} calls, {before['segments']} transcript lines")

    step("update to a rebuilt image with a no-op migration")
    current = stack.one("PRAGMA user_version")
    noop = f"{current + 1:04d}_noop_update.sql"
    update = (
        "FROM transcribr:local\nUSER root\n"
        "RUN echo '-- stack test: an update that changes nothing' > \"$(python -c"
        f" 'import transcribr.store.migrate as m; print(m.MIGRATIONS_DIR)')/{noop}\"\n"
        "USER 10001:10001\n"
    )
    built = subprocess.run(  # noqa: S603
        ["docker", "build", "-t", UPDATE_IMAGE, "-"],  # noqa: S607
        input=update, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if built.returncode != 0:
        raise StepFailed(f"building the update image failed:\n{built.stderr[-2000:]}")
    stack.env["TRANSCRIBR_IMAGE"] = UPDATE_IMAGE
    stack.compose("up", "-d", "--wait", "--wait-timeout", "300")
    version = stack.one("PRAGMA user_version")
    backups = stack.compose("exec", "-T", "web", "ls", "/data/backups").stdout.split()
    kept = any(name.startswith(f"pre-migration-v{current}-") for name in backups)
    if version != current + 1 or not kept:
        raise StepFailed(f"schema version {version} (was {current}), backups {backups}")
    if stack.snapshot() != before:
        raise StepFailed(f"data changed across the update:\n{before}\n{stack.snapshot()}")
    print(f"schema {current} -> {version}, pre-migration backup kept, data unchanged")

    step("the updated instance still collects and transcribes calls")
    stack.wait_healthy()
    stack.add_calls(AFTER_UPDATE_CALL, ends_in=20)
    stack.wait_for_state(AFTER_UPDATE_CALL, "transcribed")
    print("transcribed")
    stack.check_invariants()
    SNAPSHOT.write_text(json.dumps(stack.snapshot()), encoding="utf-8")
    print(f"snapshot saved to {SNAPSHOT} for `verify`")


def verify(stack: Stack) -> None:
    step("wait for the running stack to be healthy")
    stack.wait_healthy()
    wait_until("the worker to report in", lambda: stack.status()["worker_running"], 120)
    stack.check_invariants()
    step("compare with the snapshot saved by `resilience`")
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = stack.snapshot()
    if now != saved:
        raise StepFailed(f"data differs from the snapshot:\n{saved}\n{now}")
    print(f"same data: {len(now['calls'])} calls, {now['segments']} transcript lines")


def backlog(stack: Stack) -> None:
    step(f"queue {BACKLOG_COUNT} calls")
    stack.add_calls(BACKLOG_FIRST, ends_in=20, count=BACKLOG_COUNT)
    wait_until(
        f"{BACKLOG_COUNT} calls to be waiting",
        lambda: stack.status()["waiting"] >= BACKLOG_COUNT - 2,
        timeout=180,
    )

    step("time the home page and status API for 90 s while the backlog is processed")
    waiting_at_start = stack.status()["waiting"]
    timings: dict[str, list[float]] = {"/": [], "/api/v1/status": []}
    end = time.monotonic() + 90
    while time.monotonic() < end:
        for path, seen in timings.items():
            started = time.perf_counter()
            response = stack.web.get(path)
            seen.append(time.perf_counter() - started)
            if response.status_code != 200:
                raise StepFailed(f"{path}: HTTP {response.status_code}")
        time.sleep(0.5)
    waiting_at_end = stack.status()["waiting"]
    for path, seen in timings.items():
        print(
            f"{path}: {len(seen)} requests, median {statistics.median(seen) * 1000:.0f} ms,"
            f" slowest {max(seen) * 1000:.0f} ms"
        )
    print(f"waiting went from {waiting_at_start} to {waiting_at_end} meanwhile")
    if waiting_at_end >= waiting_at_start:
        raise StepFailed("the backlog didn't move, so this measured an idle worker")
    slowest = max(max(seen) for seen in timings.values())
    if slowest >= WEB_LATENCY_LIMIT:
        raise StepFailed(f"slowest answer took {slowest:.2f} s (limit {WEB_LATENCY_LIMIT} s)")


MODES: dict[str, Callable[[Stack], None]] = {
    "smoke": smoke,
    "resilience": resilience,
    "backlog": backlog,
    "verify": verify,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the container stack against the fake Ravon.")
    parser.add_argument("mode", nargs="?", choices=list(MODES), default="smoke")
    parser.add_argument("--keep", action="store_true", help="leave the stack running afterwards")
    args = parser.parse_args()
    stack = Stack()
    keep = args.keep or args.mode == "verify"
    try:
        if args.mode != "verify":
            stack.start_fresh()
        MODES[args.mode](stack)
    except (StepFailed, httpx.HTTPError) as failure:
        print(f"\nstack check ({args.mode}): FAILED: {failure}", flush=True)
        print(stack.compose("logs", "--tail", "40", check=False).stdout[-6000:])
        return 1
    finally:
        if not keep:
            stack.compose("down", "--volumes", check=False)
    print(f"\nstack check ({args.mode}): passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
