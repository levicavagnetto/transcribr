import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.clock import FakeClock
from transcribr.api.app import create_app
from transcribr.config import load_config
from transcribr.store.db import connect

WRITE = {"X-Transcribr": "1"}


@dataclass
class Api:
    client: TestClient
    clock: FakeClock
    data_dir: Path
    setup_codes: list[str]

    def db(self) -> sqlite3.Connection:
        return connect(self.data_dir / "transcribr.db")

    def post(
        self, path: str, json: object = None, headers: dict[str, str] | None = None
    ) -> httpx2.Response:
        return self.client.post(path, json=json, headers={**WRITE, **(headers or {})})

    def put(
        self, path: str, json: object = None, headers: dict[str, str] | None = None
    ) -> httpx2.Response:
        return self.client.put(path, json=json, headers={**WRITE, **(headers or {})})

    @property
    def setup_code(self) -> str:
        return self.setup_codes[-1]

    def create_admin(self, username: str = "admin", password: str = "workbench-lift-35s") -> None:
        response = self.post(
            "/api/v1/auth/setup",
            json={"code": self.setup_code, "username": username, "password": password},
        )
        assert response.status_code == 200, response.text

    def login(self, username: str = "admin", password: str = "workbench-lift-35s") -> None:
        response = self.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text


def make_api(
    tmp_path: Path,
    env: dict[str, str] | None = None,
    *,
    ravon_transport: httpx.BaseTransport | None = None,
) -> Iterator[Api]:
    ui = tmp_path / "ui"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<html><body>Transcribr UI</body></html>", encoding="utf-8")
    (ui / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    data = tmp_path / "data"
    config = load_config(
        {"TRANSCRIBR_DATA_DIR": str(data), "TRANSCRIBR_UI_DIR": str(ui), **(env or {})}
    )
    clock = FakeClock()
    codes: list[str] = []
    app = create_app(
        config, now=clock.utcnow, on_setup_code=codes.append, ravon_transport=ravon_transport
    )
    with TestClient(app) as client:
        yield Api(client, clock, data, codes)


@pytest.fixture
def api(tmp_path: Path) -> Iterator[Api]:
    yield from make_api(tmp_path)


@pytest.fixture
def admin(api: Api) -> Api:
    api.create_admin()
    api.login()
    return api
