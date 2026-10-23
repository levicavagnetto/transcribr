"""Run the real container stack against the fake Ravon with the worker offline.

    uv run --directory backend ../scripts/stack_check.py [--keep]

Builds the images, starts web + worker + fake Ravon (backend/tests/stack), creates the admin
from the setup code in the web log, chooses a queue, adds a fixture call to the fake and waits
until the worker has transcribed it. The worker has no network except its loopback, so this
also shows a running instance downloads nothing. Removes the stack and its volume afterwards
unless --keep is given. Needs Docker; exits non-zero on the first failed step.
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

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
CALL_ID = 90001001
TRANSCRIBE_TIMEOUT = 600


class StepFailed(Exception):
    pass


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - fixed docker command
        [*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise StepFailed(f"docker compose {' '.join(args)} failed:\n{result.stderr[-3000:]}")
    return result


def step(name: str) -> None:
    print(f"\n== {name} ==", flush=True)


def setup_code() -> str:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        match = re.search(r"Admin setup code: ([A-Z0-9-]+)", compose("logs", "web").stdout)
        if match:
            return match.group(1)
        time.sleep(2)
    raise StepFailed("no admin setup code in the web log")


def run() -> None:
    step("build the runtime and test images")
    compose("build")

    step("start web, worker and the fake Ravon")
    compose("up", "-d", "--wait", "--wait-timeout", "300")
    print(compose("ps", "--format", "{{.Service}}: {{.Status}}").stdout.strip())

    step("check the worker can't reach the internet")
    probe = compose(
        "exec", "-T", "worker", "python", "-c",
        "import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)",
        check=False,
    )  # fmt: skip
    if probe.returncode == 0:
        raise StepFailed("the worker reached 1.1.1.1; the offline overlay isn't in effect")
    print("no route out, as intended")

    with httpx.Client(base_url=BASE_URL, timeout=10) as web:
        step("create the admin from the logged setup code and choose a queue")
        response = web.post(
            "/api/v1/auth/setup",
            headers=WRITE,
            json={"code": setup_code(), "username": "admin", "password": "stack test passphrase"},
        )
        if response.status_code != 200:
            raise StepFailed(f"admin setup: HTTP {response.status_code} {response.text}")
        polled_before = web.get("/api/v1/status").json()["last_poll_ok"]
        response = web.put(
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

        # The worker starts following a newly chosen queue at its next poll; calls that end
        # before then count as missed, so wait for that poll before adding the call.
        step("wait for the worker's first poll of the chosen queue")
        deadline = time.monotonic() + 120
        while web.get("/api/v1/status").json()["last_poll_ok"] == polled_before:
            if time.monotonic() > deadline:
                raise StepFailed("the worker didn't poll within 2 minutes of the settings change")
            time.sleep(3)

        # A call still in progress: it ends after the queue was followed, while the worker runs.
        step("add a call that ends in 20 s and wait for its transcript")
        compose(
            "exec", "-T", "fake-ravon", "python", "-m", "tests.fake_ravon.serve",
            "add-call", str(CALL_ID), "--queue", QUEUE, "--audio", "two-voices",
            "--ended-seconds-ago=-20",
        )  # fmt: skip
        deadline = time.monotonic() + TRANSCRIBE_TIMEOUT
        status: dict[str, object] = {}
        while time.monotonic() < deadline:
            status = web.get("/api/v1/status").json()
            if status["failed_last_24h"]:
                raise StepFailed(f"the call failed: {status}")
            if status["transcribed_today"]:
                break
            time.sleep(5)
        else:
            raise StepFailed(f"not transcribed within {TRANSCRIBE_TIMEOUT} s: {status}")
        print(
            f"listed {status['listed_today']}, transcribed {status['transcribed_today']},"
            f" Ravon {status['ravon_state']}, worker running {status['worker_running']}"
        )
        if status["ravon_state"] != "ok" or status["guard_violations"]:
            raise StepFailed(f"unexpected status: {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="leave the stack running afterwards")
    keep = parser.parse_args().keep
    try:
        run()
    except (StepFailed, httpx.HTTPError) as failure:
        print(f"\nstack check: FAILED: {failure}", flush=True)
        print(compose("logs", "--tail", "40", check=False).stdout[-6000:])
        return 1
    finally:
        if not keep:
            compose("down", "--volumes", check=False)
    print("\nstack check: passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
