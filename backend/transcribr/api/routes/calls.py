"""Open call actions: request transcription, and list earlier calls."""

from fastapi import APIRouter

from transcribr.api.deps import ApiError, Db, Now
from transcribr.store.calls import request_transcription
from transcribr.worker import request_load_earlier

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])


@router.post("/{call_id}/transcribe")
def transcribe(call_id: int, conn: Db, now: Now) -> dict[str, object]:
    """Queue a Not transcribed or Failed call. A call in any other state is left alone."""
    row = conn.execute("SELECT state FROM calls WHERE id = ?", (call_id,)).fetchone()
    if row is None:
        raise ApiError(404, "call_not_found", f"No call {call_id} is listed.")
    queued = request_transcription(conn, call_id, now)
    state = conn.execute("SELECT state FROM calls WHERE id = ?", (call_id,)).fetchone()[0]
    return {"queued": queued, "state": state}


@router.post("/load-earlier")
def load_earlier(conn: Db, now: Now) -> dict[str, bool]:
    """Ask the worker to list the 7 days before the earliest time already listed."""
    pending = conn.execute("SELECT 1 FROM jobs WHERE type = 'load_earlier'").fetchone()
    if pending is None:
        request_load_earlier(conn, now)
    return {"requested": True}
