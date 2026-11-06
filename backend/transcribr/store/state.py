"""Small runtime facts shared between the web and worker services, as JSON values."""

import json
import sqlite3
from typing import Any

from transcribr.timeutil import to_iso, utcnow

LAST_POLL_OK = "last_poll_ok_at"
RAVON_STATE = (
    "ravon_state"  # ok | login_failed | unreachable | no_credentials | page_format_changed
)
RAVON_ERROR = "ravon_error"
RAVON_REJECTED_FINGERPRINT = "ravon_rejected_fingerprint"
QUEUES_FOLLOWED_SINCE = "queues_followed_since"
GUARD_VIOLATIONS = "guard_violations"
RETRY_LOGIN_REQUESTED = (
    "ravon_retry_login_requested"  # set by the web service, cleared by the worker
)
CHECK_REQUESTED = (
    "ravon_check_requested"  # "Check Ravon now": set by the web, cleared by the worker
)
QUEUE_LIST = (
    "ravon_queue_list"  # {"fetched_at": ..., "queues": [{"value", "label"}]}, kept by the worker
)
QUEUE_REFRESH_REQUESTED = "ravon_queue_refresh_requested"  # set by the web service
LISTED_FROM = "listed_from"  # the earliest time already listed; "load earlier" goes before it


class State:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM service_state WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO service_state (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE"
            " SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value), to_iso(utcnow())),
        )

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM service_state WHERE key = ?", (key,))
