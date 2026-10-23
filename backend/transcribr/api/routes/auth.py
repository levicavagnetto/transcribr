"""Admin setup, login and logout: the only admin-related endpoints reachable without a session."""

import math
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from transcribr.admin import SESSION_LIFETIME, AdminError, FailureLimiter
from transcribr.api.deps import SESSION_COOKIE, AdminsDep, ApiError, Now

router = APIRouter(prefix="/api/v1/auth", tags=["admin login"])


class AuthState(BaseModel):
    state: Literal["setup_required", "login_required", "logged_in"]
    username: str | None = None


class Setup(BaseModel):
    code: str
    username: str
    password: str


class Login(BaseModel):
    username: str
    password: str


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limiter(request: Request) -> FailureLimiter:
    limiter: FailureLimiter = request.app.state.limiter
    return limiter


def _check_not_blocked(request: Request, now: Now) -> None:
    wait = _limiter(request).retry_after(_client(request), now)
    if wait > 0:
        seconds = math.ceil(wait)
        raise ApiError(
            429,
            "too_many_attempts",
            f"Too many failed attempts. Try again in {seconds} seconds.",
            retry_after=seconds,
        )


def _set_session(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/state")
def state(request: Request, admins: AdminsDep) -> AuthState:
    if not admins.exists():
        return AuthState(state="setup_required")
    if admins.session_valid(request.cookies.get(SESSION_COOKIE)):
        return AuthState(state="logged_in", username=admins.username())
    return AuthState(state="login_required")


@router.post("/setup")
def setup(
    body: Setup, request: Request, response: Response, admins: AdminsDep, now: Now
) -> AuthState:
    _check_not_blocked(request, now)
    try:
        admins.setup(body.code, body.username, body.password)
    except AdminError as error:
        if error.code == "wrong_setup_code":
            _limiter(request).failed(_client(request), now)
            request.app.state.log.warning("wrong admin setup code from %s", _client(request))
        status = 409 if error.code == "admin_exists" else 422
        raise ApiError(status, error.code, error.message) from None
    _limiter(request).succeeded(_client(request))
    _set_session(request, response, admins.start_session())
    request.app.state.log.info("admin account created")
    return AuthState(state="logged_in", username=admins.username())


@router.post("/login")
def login(
    body: Login, request: Request, response: Response, admins: AdminsDep, now: Now
) -> AuthState:
    _check_not_blocked(request, now)
    if not admins.check_credentials(body.username, body.password):
        _limiter(request).failed(_client(request), now)
        request.app.state.log.warning(
            "failed admin login from %s for username %r", _client(request), body.username
        )
        raise ApiError(401, "wrong_login", "Wrong username or password.")
    _limiter(request).succeeded(_client(request))
    _set_session(request, response, admins.start_session())
    return AuthState(state="logged_in", username=admins.username())


@router.post("/logout")
def logout(request: Request, response: Response, admins: AdminsDep) -> AuthState:
    admins.end_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return AuthState(state="login_required" if admins.exists() else "setup_required")
