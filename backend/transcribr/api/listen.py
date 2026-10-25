"""The web service's own Ravon session, used only to fetch a recording for Listen (design D3).

It goes through the same guarded, paced client as the worker, so the read-only allow list
applies, and audio is held in memory only for the response. It respects a login the worker
found rejected, and tries again once the worker's retry clears that.
"""

import sqlite3
import threading
from pathlib import Path

import httpx

from transcribr.config import Config
from transcribr.ravon.client import MIN_REQUEST_INTERVAL, RavonClient
from transcribr.store.calls import is_listed
from transcribr.store.db import connect
from transcribr.store.state import RAVON_REJECTED_FINGERPRINT, State


class WebRavon:
    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.BaseTransport | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL,
    ) -> None:
        self._config = config
        self._transport = transport
        self._min_interval = min_interval
        self._client: RavonClient | None = None
        self._lock = threading.Lock()

    def _is_listed(self, recording_id: int) -> bool:
        conn = connect(Path(self._config.database_path))
        try:
            return is_listed(conn)(recording_id)
        finally:
            conn.close()

    def fetch(self, conn: sqlite3.Connection, recording_id: int) -> bytes:
        """The recording's MP3 bytes. Raises the client's RavonError subclasses."""
        rejected: str | None = State(conn).get(RAVON_REJECTED_FINGERPRINT)
        with self._lock:
            if self._client is None:
                password = self._config.ravon_password
                self._client = RavonClient(
                    self._config.ravon_base_url,
                    self._config.ravon_username,
                    password.get_secret_value() if password else None,
                    transport=self._transport,
                    is_known_recording=self._is_listed,
                    rejected_fingerprint=rejected,
                    min_interval=self._min_interval,
                )
            elif rejected is None and self._client.login_state == "rejected":
                self._client.retry_login()  # the worker's retry cleared the rejected login
            client = self._client
        return client.download(recording_id)

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
