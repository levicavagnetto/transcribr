import json
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.fake_ravon.serve import FIXTURES, Site, start
from transcribr.ravon.client import RavonClient


@pytest.fixture
def served() -> Iterator[tuple[Site, str, int]]:
    site, site_server, control_server = start(0, 0)
    yield site, f"http://127.0.0.1:{site_server.server_port}", control_server.server_port
    for server in (site_server, control_server):
        server.shutdown()
        server.server_close()


def test_the_real_client_reads_the_served_fake(served: tuple[Site, str, int]) -> None:
    site, url, control_port = served
    request = urllib.request.Request(
        f"http://127.0.0.1:{control_port}/calls",
        data=json.dumps({"id": 90000501, "minutes": 0.5, "ended_seconds_ago": 5}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - local test server
        assert json.loads(response.read())["id"] == 90000501

    client = RavonClient(url, site.fake.username, site.fake.password, min_interval=0)
    try:
        assert [q.value for q in client.queues()] == list(site.fake.queues)
        local_now = datetime.now(ZoneInfo(site.fake.zone)).replace(tzinfo=None)
        found = client.search(
            "tireProz-salescustserv", local_now - timedelta(hours=1), local_now + timedelta(hours=1)
        )
        assert [r.id for r in found] == [90000501]
        assert client.download(90000501) == (FIXTURES / "two-voices.mp3").read_bytes()
    finally:
        client.close()
