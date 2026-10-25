"""The web service: the REST API and the built web UI (design D9)."""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from transcribr.admin import Admins, FailureLimiter
from transcribr.api.deps import WRITE_HEADER, ApiError
from transcribr.api.listen import WebRavon
from transcribr.api.routes import admin, auth, calls, system
from transcribr.config import Config
from transcribr.store.db import connect
from transcribr.store.migrate import migrate
from transcribr.timeutil import utcnow

log = logging.getLogger("transcribr.web")

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _error(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def _log_setup_code(code: str) -> None:
    log.warning("=" * 60)
    log.warning("No admin account yet. Admin setup code: %s", code)
    log.warning("Open the web app, follow the footer Admin link, and enter this code.")
    log.warning("=" * 60)


def create_app(
    config: Config,
    *,
    now: Callable[[], datetime] = utcnow,
    on_setup_code: Callable[[str], None] = _log_setup_code,
    ravon_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    """`ravon_transport` lets tests put the fake Ravon behind Listen."""
    ravon = WebRavon(config, transport=ravon_transport, min_interval=0 if ravon_transport else 1)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        migrate(config.database_path)
        conn = connect(config.database_path)
        try:
            admins = Admins(conn, now=now)
            if not admins.exists():
                on_setup_code(admins.new_setup_code())
        finally:
            conn.close()
        yield
        ravon.close()

    app = FastAPI(
        title="Transcribr",
        version="1",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.config = config
    app.state.now = now
    app.state.limiter = FailureLimiter()
    app.state.ravon = ravon
    app.state.log = log

    @app.middleware("http")
    async def require_write_header(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            request.url.path.startswith("/api/")
            and request.method not in _SAFE_METHODS
            and request.headers.get(WRITE_HEADER) != "1"
        ):
            return _error(
                403, "missing_request_header", f"API writes need the {WRITE_HEADER}: 1 header."
            )
        return await call_next(request)

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, error: ApiError) -> JSONResponse:
        return _error(error.status, error.code, error.message, **error.extra)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if error.status_code == 404 else f"http_{error.status_code}"
        return _error(error.status_code, code, str(error.detail))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, error: RequestValidationError) -> JSONResponse:
        errors: list[dict[str, Any]] = list(error.errors())
        first: dict[str, Any] = errors[0] if errors else {}
        location: tuple[object, ...] = tuple(first.get("loc", ()))
        where = ".".join(str(part) for part in location)
        return _error(422, "invalid_request", f"{where}: {first.get('msg', 'invalid')}")

    for module in (system, calls, auth, admin):
        app.include_router(module.router)

    ui_dir = config.ui_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            return _error(404, "not_found", "Not Found")
        if path:
            candidate = (ui_dir / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(ui_dir):
                return FileResponse(candidate)
            if Path(path).suffix:  # a missing asset, not a page of the app
                return _error(404, "not_found", "Not Found")
        index = ui_dir / "index.html"
        if not index.is_file():
            return _error(503, "ui_missing", "The web UI has not been built into this instance.")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
