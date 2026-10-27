"""Admin-only endpoints. The router-level dependency refuses every request without a session."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from transcribr.admin import AdminError
from transcribr.api.deps import AdminsDep, AdminSession, ApiError, Db, Now, require_admin
from transcribr.attribution.matching import REMATCH_SETTINGS
from transcribr.attribution.queue import request_rematch
from transcribr.settings import Setting, SettingError, Settings, registered
from transcribr.store.state import (
    QUEUE_LIST,
    QUEUE_REFRESH_REQUESTED,
    RETRY_LOGIN_REQUESTED,
    State,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class PasswordChange(BaseModel):
    current: str
    new: str


def _field(setting: Setting[Any]) -> dict[str, Any]:
    """A setting's label, message and default, plus the limits the UI checks as you type."""
    field: dict[str, Any] = {
        "key": setting.key,
        "label": setting.label,
        "message": setting.message,
        "default": setting.default,
    }
    schema = setting.adapter.json_schema()
    for limit, name in (
        ("minimum", "minimum"),
        ("maximum", "maximum"),
        ("minLength", "min_length"),
        ("maxLength", "max_length"),
    ):
        if limit in schema:
            field[name] = schema[limit]
    return field


@router.get("/settings")
def get_settings(conn: Db) -> dict[str, Any]:
    return {
        "values": Settings(conn).as_dict(),
        "fields": [_field(s) for s in registered().values()],
    }


@router.put("/settings")
def put_settings(changes: dict[str, Any], conn: Db, now: Now) -> dict[str, Any]:
    """Change one or more settings. All are validated, together, before any is saved."""
    known = registered()
    for key in changes:
        if key not in known:
            raise ApiError(422, "unknown_setting", f"There is no setting called {key!r}.", key=key)
    settings = Settings(conn)
    before = settings.as_dict()
    try:
        settings.set_many(changes)
    except SettingError as error:
        raise ApiError(422, "invalid_setting", error.message, key=error.key) from None
    after = settings.as_dict()
    if any(before[key] != after[key] for key in REMATCH_SETTINGS):
        request_rematch(conn, now)
    return get_settings(conn)


@router.get("/queues")
def queues(conn: Db) -> dict[str, Any]:
    """The Ravon queue list as the worker last read it (this never contacts Ravon)."""
    cached: dict[str, Any] | None = State(conn).get(QUEUE_LIST)
    return {
        "queues": cached["queues"] if cached else [],
        "fetched_at": cached["fetched_at"] if cached else None,
        "refresh_requested": bool(State(conn).get(QUEUE_REFRESH_REQUESTED)),
    }


@router.post("/queues/refresh")
def refresh_queues(conn: Db) -> dict[str, bool]:
    State(conn).set(QUEUE_REFRESH_REQUESTED, True)
    return {"requested": True}


@router.post("/ravon/retry-login")
def retry_login(conn: Db) -> dict[str, bool]:
    State(conn).set(RETRY_LOGIN_REQUESTED, True)
    return {"requested": True}


@router.post("/password")
def change_password(
    body: PasswordChange, token: AdminSession, admins: AdminsDep
) -> dict[str, bool]:
    try:
        admins.change_password(token, body.current, body.new)
    except AdminError as error:
        raise ApiError(422, error.code, error.message) from None
    return {"changed": True}
