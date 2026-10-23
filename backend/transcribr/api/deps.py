"""Shared pieces for the API routes: errors, the database, the clock and the admin check."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request

from transcribr.admin import Admins, FailureLimiter
from transcribr.config import Config
from transcribr.store.db import connect

SESSION_COOKIE = "transcribr_admin"
WRITE_HEADER = "X-Transcribr"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def get_config(request: Request) -> Config:
    config: Config = request.app.state.config
    return config


def get_now(request: Request) -> datetime:
    now: Callable[[], datetime] = request.app.state.now
    return now()


def get_limiter(request: Request) -> FailureLimiter:
    limiter: FailureLimiter = request.app.state.limiter
    return limiter


def get_db(config: Annotated[Config, Depends(get_config)]) -> Iterator[sqlite3.Connection]:
    conn = connect(config.database_path)
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]


def get_admins(request: Request, conn: Db) -> Admins:
    return Admins(conn, now=request.app.state.now)


AdminsDep = Annotated[Admins, Depends(get_admins)]


def require_admin(request: Request, admins: AdminsDep) -> str:
    """The admin's session token; refuses the request without a valid session."""
    token = request.cookies.get(SESSION_COOKIE)
    if token is None or not admins.session_valid(token):
        raise ApiError(401, "admin_login_required", "Log in as the admin first.")
    return token


AdminSession = Annotated[str, Depends(require_admin)]
