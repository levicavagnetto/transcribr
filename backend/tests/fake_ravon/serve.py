"""Serve the fake Ravon over HTTP for the container stack tests (tests/stack).

    python -m tests.fake_ravon.serve                 # run the server
    python -m tests.fake_ravon.serve add-call ID ... # add a call through the control port

The fake site listens on 127.0.0.1:8090 and the control port on 127.0.0.1:8091. In the
test stack this process shares the worker's network namespace, so the worker reaches it on
127.0.0.1, the only plain-http address its allow list accepts. It holds only invented data.
"""

import argparse
import json
import sys
import threading
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from tests.fake_ravon.app import DATE_FORMAT, FakeCall, FakeRavon

HOST = "127.0.0.1"
SITE_PORT = 8090
CONTROL_PORT = 8091
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


def _now() -> datetime:
    return datetime.now(UTC)


class Site:
    def __init__(self) -> None:
        self.fake = FakeRavon(now=_now)
        self.lock = threading.Lock()

    def add_call(  # noqa: PLR0917 - one value per call field
        self,
        rid: int,
        queue: str,
        minutes: float,
        ended_seconds_ago: float,
        audio: str,
        caller: str = "(405) 555-0100",
    ):
        start = _now() - timedelta(seconds=ended_seconds_ago) - timedelta(minutes=minutes)
        local = start.astimezone(ZoneInfo(self.fake.zone)).strftime(DATE_FORMAT)
        call = FakeCall(
            rid,
            queue,
            local,
            minutes,
            caller=caller,
            audio=(FIXTURES / f"{audio}.mp3").read_bytes(),
        )
        with self.lock:
            self.fake.calls.append(call)
        return {"id": rid, "start_local": local}


def _site_handler(site: Site) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            request = httpx.Request(
                self.command,
                f"http://{HOST}:{SITE_PORT}{self.path}",
                headers=dict(self.headers.items()),
                content=self.rfile.read(length) if length else b"",
            )
            try:
                with site.lock:
                    response = site.fake.handle(request)
            except AssertionError as error:  # the fake refuses requests the real site must not get
                response = httpx.Response(500, text=f"fake Ravon refused the request: {error}")
            body = response.content
            self.send_response(response.status_code)
            for name, value in response.headers.multi_items():
                if name.lower() not in {"content-length", "transfer-encoding", "connection"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _forward

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write(f"fake-ravon {self.command} {self.path.split('?')[0]}\n")

    return Handler


def _control_handler(site: Site) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/calls":
                reply = site.add_call(
                    int(body["id"]),
                    body.get("queue", "tireProz-salescustserv"),
                    float(body.get("minutes", 0.5)),
                    float(body.get("ended_seconds_ago", 5)),
                    body.get("audio", "two-voices"),
                    body.get("caller", "(405) 555-0100"),
                )
            else:
                self.send_error(404)
                return
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def start(
    site_port: int = SITE_PORT, control_port: int = CONTROL_PORT
) -> tuple[Site, ThreadingHTTPServer, ThreadingHTTPServer]:
    """Start both servers on background threads (port 0 picks a free port)."""
    site = Site()
    servers = (
        ThreadingHTTPServer((HOST, site_port), _site_handler(site)),
        ThreadingHTTPServer((HOST, control_port), _control_handler(site)),
    )
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return site, *servers


def serve() -> None:
    _, site_server, control_server = start()
    print(
        f"fake Ravon on http://{HOST}:{site_server.server_port},"
        f" control on :{control_server.server_port}",
        flush=True,
    )
    threading.Event().wait()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.fake_ravon.serve")
    commands = parser.add_subparsers(dest="command")
    add = commands.add_parser("add-call", help="add a call that ended a moment ago")
    add.add_argument("id", type=int)
    add.add_argument("--queue", default="tireProz-salescustserv")
    add.add_argument("--minutes", type=float, default=0.5)
    add.add_argument("--ended-seconds-ago", type=float, default=5)
    add.add_argument("--audio", choices=["two-voices", "silence"], default="two-voices")
    add.add_argument("--caller", default="(405) 555-0100")
    add.add_argument("--count", type=int, default=1, help="add this many calls, IDs counting up")
    args = parser.parse_args(argv)
    if args.command is None:
        serve()
        return 0
    for rid in range(args.id, args.id + args.count):
        payload = json.dumps(
            {
                "id": rid,
                "queue": args.queue,
                "minutes": args.minutes,
                "ended_seconds_ago": args.ended_seconds_ago,
                "audio": args.audio,
                "caller": args.caller,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://{HOST}:{CONTROL_PORT}/calls",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - local URL
            print(response.read().decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
