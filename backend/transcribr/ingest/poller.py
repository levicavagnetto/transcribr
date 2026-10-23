"""Listing calls from Ravon and deciding which are transcribed automatically (design D4, D5)."""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from transcribr.ingest.uptime import Uptime
from transcribr.ravon.client import (
    LoginRejected,
    NoCredentials,
    RavonClient,
    RavonError,
    RavonUnavailable,
)
from transcribr.ravon.parse import PageFormatChanged
from transcribr.settings import STORE_QUEUES, TIME_ZONE, Settings
from transcribr.store.calls import add_listed, call_times, newest_start_utc, oldest_start_utc
from transcribr.store.state import (
    LAST_POLL_OK,
    LISTED_FROM,
    QUEUES_FOLLOWED_SINCE,
    RAVON_ERROR,
    RAVON_REJECTED_FINGERPRINT,
    RAVON_STATE,
    State,
)
from transcribr.timeutil import from_iso, to_iso, utc_to_local, utcnow

log = logging.getLogger(__name__)

POLL_OVERLAP = timedelta(hours=2)
CATCH_UP_OVERLAP = timedelta(days=1)
FIRST_START_LISTING = timedelta(days=7)
LOAD_EARLIER_STEP = timedelta(days=7)


@dataclass(frozen=True)
class PollResult:
    ok: bool
    state: str
    listed: int = 0
    queued: int = 0


class Poller:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: RavonClient,
        uptime: Uptime,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._conn = conn
        self._client = client
        self._uptime = uptime
        self._now = now
        self._settings = Settings(conn)
        self._state = State(conn)

    def poll(self) -> PollResult:
        """List calls since shortly before the last successful poll."""
        now = self._now()
        last_ok = self._state.get(LAST_POLL_OK)
        start = (from_iso(last_ok) if last_ok else now) - POLL_OVERLAP
        return self._list(start, now, now, mark_success=True)

    def catch_up(self) -> PollResult:
        """On start: list what happened while the worker was off (first start: the last 7 days)."""
        now = self._now()
        newest = newest_start_utc(self._conn)
        start = from_iso(newest) - CATCH_UP_OVERLAP if newest else now - FIRST_START_LISTING
        result = self._list(start, now, now, mark_success=True)
        if result.ok and self._state.get(LISTED_FROM) is None:
            self._state.set(LISTED_FROM, to_iso(start))
        return result

    def load_earlier(self) -> PollResult:
        """List the 7 days before the earliest time already listed, and move that boundary."""
        now = self._now()
        boundary = self._state.get(LISTED_FROM) or oldest_start_utc(self._conn)
        end = from_iso(boundary) if boundary else now
        result = self._list(end - LOAD_EARLIER_STEP, end, now, mark_success=False)
        if result.ok:
            self._state.set(LISTED_FROM, to_iso(end - LOAD_EARLIER_STEP))
        return result

    def _followed_queues(self, now: datetime) -> dict[str, datetime]:
        """The selected queues and when each was first followed; new ones start now."""
        selected = self._settings.get(STORE_QUEUES)
        stored: dict[str, str] = self._state.get(QUEUES_FOLLOWED_SINCE, {})
        followed = {q: stored.get(q, to_iso(now)) for q in selected}
        if followed != stored:
            self._state.set(QUEUES_FOLLOWED_SINCE, followed)
        return {q: from_iso(since) for q, since in followed.items()}

    def _list(
        self, start: datetime, end: datetime, now: datetime, *, mark_success: bool
    ) -> PollResult:
        queues = self._followed_queues(now)
        if not queues:
            return PollResult(ok=False, state="no_queues")
        zone = self._settings.get(TIME_ZONE)
        listed = queued = 0
        try:
            for queue, since in queues.items():
                found = self._client.search(
                    queue, utc_to_local(start, zone), utc_to_local(end, zone)
                )
                for recording in found:
                    _, ended = call_times(recording, zone)
                    auto = ended >= since and self._uptime.was_running(ended)
                    if add_listed(
                        self._conn, recording, queue=queue, zone=zone, now=now, auto_queue=auto
                    ):
                        listed += 1
                        queued += int(auto)
        except NoCredentials as error:
            return self._failed("no_credentials", error)
        except LoginRejected as error:
            self._state.set(RAVON_REJECTED_FINGERPRINT, self._client.rejected_fingerprint)
            return self._failed("login_failed", error)
        except PageFormatChanged as error:
            return self._failed("page_format_changed", error)
        except (RavonUnavailable, RavonError) as error:
            return self._failed("unreachable", error)
        if mark_success:
            self._state.set(LAST_POLL_OK, to_iso(now))
        self._state.set(RAVON_STATE, "ok")
        self._state.delete(RAVON_ERROR)
        if listed:
            log.info("listed %d new calls (%d queued for transcription)", listed, queued)
        return PollResult(ok=True, state="ok", listed=listed, queued=queued)

    def _failed(self, state: str, error: Exception) -> PollResult:
        self._state.set(RAVON_STATE, state)
        self._state.set(RAVON_ERROR, str(error))
        log.warning("listing calls failed (%s): %s", state, error)
        return PollResult(ok=False, state=state)
