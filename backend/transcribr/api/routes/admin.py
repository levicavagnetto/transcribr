"""Admin-only endpoints. The router-level dependency refuses every request without a session."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from transcribr.admin import AdminError
from transcribr.api.deps import AdminsDep, AdminSession, ApiError, Db, require_admin
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


def _field(setting: Setting[Any]) -> dict[str, str]:
    return {"key": setting.key, "label": setting.label}


@router.get("/settings")
def get_settings(conn: Db) -> dict[str, Any]:
    return {
        "values": Settings(conn).as_dict(),
        "fields": [_field(s) for s in registered().values()],
    }


@router.put("/settings")
def put_settings(changes: dict[str, Any], conn: Db) -> dict[str, Any]:
    """Change one or more settings. All are validated before any is saved."""
    settings = Settings(conn)
    known = registered()
    cleaned: dict[str, Any] = {}
    for key, value in changes.items():
        setting = known.get(key)
        if setting is None:
            raise ApiError(422, "unknown_setting", f"There is no setting called {key!r}.", key=key)
        try:
            cleaned[key] = setting.adapter.validate_python(value)
        except ValueError:
            raise ApiError(422, "invalid_setting", setting.message, key=key) from None
    try:
        for key, value in cleaned.items():
            settings.set_by_key(key, value)
    except SettingError as error:  # pragma: no cover - values were validated above
        raise ApiError(422, "invalid_setting", error.message, key=error.key) from None
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
