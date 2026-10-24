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

    def add_calls(self, first: int, *, ends_in: float, count: int = 1) -> None:
        self.compose(
            "exec", "-T", "fake-ravon", "python", "-m", "tests.fake_ravon.serve",
            "add-call", str(first), "--queue", QUEUE, "--audio", "two-voices",
            f"--ended-seconds-ago={-ends_in}", "--count", str(count),
        )  # fmt: skip

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
    step("a call that ends while the worker runs is transcribed automatically")
    stack.add_calls(AUTO_CALL, ends_in=20)
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
    stack.check_invariants()


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
