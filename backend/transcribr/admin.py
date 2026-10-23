"""The single admin account: first-visit setup code, password, sessions (design D12)."""

import hashlib
import hmac
import secrets
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from transcribr.store.db import transaction
from transcribr.timeutil import from_iso, to_iso, utcnow

SESSION_LIFETIME = timedelta(hours=12)
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
MAX_USERNAME_LENGTH = 64
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
_CODE_LENGTH = 10

_hasher = PasswordHasher()


class AdminError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:8]}-{code[8:]}"


def _normalize_code(entered: str) -> str:
    return "".join(ch for ch in entered.upper() if ch.isalnum())


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminError(
            "password_too_short",
            f"The password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AdminError(
            "password_too_long", f"Keep the password under {MAX_PASSWORD_LENGTH} characters."
        )


class Admins:
    def __init__(self, conn: sqlite3.Connection, *, now: Callable[[], datetime] = utcnow) -> None:
        self._conn = conn
        self._now = now

    def exists(self) -> bool:
        return self._conn.execute("SELECT 1 FROM admin").fetchone() is not None

    def username(self) -> str | None:
        row = self._conn.execute("SELECT username FROM admin").fetchone()
        return None if row is None else str(row["username"])

    def new_setup_code(self) -> str:
        """Store the hash of a fresh one-time code and return the code (formatted)."""
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        self._conn.execute(
            "INSERT INTO admin_setup_code (id, code_hash, created_at) VALUES (1, ?, ?)"
            " ON CONFLICT (id) DO UPDATE SET code_hash = excluded.code_hash,"
            " created_at = excluded.created_at",
            (_sha256(code), to_iso(self._now())),
        )
        return format_code(code)

    def setup(self, code: str, username: str, password: str) -> None:
        name = username.strip()
        if not name or len(name) > MAX_USERNAME_LENGTH:
            raise AdminError(
                "invalid_username", f"Use a username of 1 to {MAX_USERNAME_LENGTH} characters."
            )
        check_new_password(password)
        with transaction(self._conn):
            if self.exists():
                raise AdminError("admin_exists", "An admin account already exists.")
            row = self._conn.execute("SELECT code_hash FROM admin_setup_code").fetchone()
            if row is None or not hmac.compare_digest(
                row["code_hash"], _sha256(_normalize_code(code))
            ):
                raise AdminError("wrong_setup_code", "That setup code is not right.")
            self._conn.execute(
                "INSERT INTO admin (id, username, password_hash, password_changed_at)"
                " VALUES (1, ?, ?, ?)",
                (name, _hasher.hash(password), to_iso(self._now())),
            )
            self._conn.execute("DELETE FROM admin_setup_code")

    def check_credentials(self, username: str, password: str) -> bool:
        row = self._conn.execute("SELECT username, password_hash FROM admin").fetchone()
        if row is None:
            return False
        try:
            _hasher.verify(row["password_hash"], password)
        except VerificationError, InvalidHashError:
            return False
        if not hmac.compare_digest(str(row["username"]), username.strip()):
            return False
        if _hasher.check_needs_rehash(row["password_hash"]):
            self._conn.execute("UPDATE admin SET password_hash = ?", (_hasher.hash(password),))
        return True

    def start_session(self) -> str:
        token = secrets.token_urlsafe(32)
        now = self._now()
        self._conn.execute(
            "INSERT INTO admin_sessions (id_hash, created_at, expires_at) VALUES (?, ?, ?)",
            (_sha256(token), to_iso(now), to_iso(now + SESSION_LIFETIME)),
        )
        self._conn.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (to_iso(now),))
        return token

    def session_valid(self, token: str | None) -> bool:
        if not token:
            return False
        row = self._conn.execute(
            "SELECT expires_at FROM admin_sessions WHERE id_hash = ?", (_sha256(token),)
        ).fetchone()
        return row is not None and from_iso(row["expires_at"]) > self._now()

    def end_session(self, token: str | None) -> None:
        if token:
            self._conn.execute("DELETE FROM admin_sessions WHERE id_hash = ?", (_sha256(token),))

    def change_password(self, token: str, current: str, new: str) -> None:
        username = self.username() or ""
        if not self.check_credentials(username, current):
            raise AdminError("wrong_password", "The current password is not right.")
        check_new_password(new)
        with transaction(self._conn):
            self._conn.execute(
                "UPDATE admin SET password_hash = ?, password_changed_at = ?",
                (_hasher.hash(new), to_iso(self._now())),
            )
            self._conn.execute("DELETE FROM admin_sessions WHERE id_hash != ?", (_sha256(token),))

    def reset(self) -> str:
        """Remove the admin and every session, and return a new setup code."""
        with transaction(self._conn):
            self._conn.execute("DELETE FROM admin")
            self._conn.execute("DELETE FROM admin_sessions")
        return self.new_setup_code()


@dataclass
class _Client:
    failures: list[datetime] = field(default_factory=list[datetime])
    blocked_until: datetime | None = None
    blocks: int = 0


class FailureLimiter:
    """Slows down guessing: 5 failures within a minute block the client, doubling each time."""

    WINDOW = timedelta(minutes=1)
    LIMIT = 5
    FIRST_BLOCK = timedelta(seconds=30)
    MAX_BLOCK = timedelta(minutes=15)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, _Client] = {}

    def retry_after(self, client: str, now: datetime) -> float:
        """Seconds the client must wait, or 0 if it may try now."""
        with self._lock:
            state = self._clients.get(client)
            if state is None or state.blocked_until is None or state.blocked_until <= now:
                return 0.0
            return (state.blocked_until - now).total_seconds()

    def failed(self, client: str, now: datetime) -> None:
        with self._lock:
            state = self._clients.setdefault(client, _Client())
            state.failures = [t for t in state.failures if now - t < self.WINDOW] + [now]
            if len(state.failures) >= self.LIMIT:
                block = min(self.MAX_BLOCK, self.FIRST_BLOCK * 2**state.blocks)
                state.blocked_until = now + block
                state.blocks += 1
                state.failures = []

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._clients.pop(client, None)
