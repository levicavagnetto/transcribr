"""Open call endpoints: the call list and search, one call, its transcript, and call actions.

The response models carry no voiceprint field, so voiceprints cannot leak by accident.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import AwareDatetime, BaseModel

from transcribr.api.deps import ApiError, Db, Now, Ravon
from transcribr.ravon.client import LoginRejected, NoCredentials, RavonError
from transcribr.ravon.guard import ReadOnlyViolation
from transcribr.settings import TIME_ZONE, Settings
from transcribr.store import browse
from transcribr.store.calls import request_transcription
from transcribr.worker import request_load_earlier

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

CallState = Literal["not_transcribed", "waiting", "processing", "transcribed", "failed"]


class PassagePart(BaseModel):
    text: str
    hit: bool


class Passage(BaseModel):
    """Where a text search matched: the segment's start time and the words around the match."""

    at_s: float
    parts: list[PassagePart]


class CallSummary(BaseModel):
    id: int
    queue: str
    start_local: str
    start_utc: str
    minutes: float
    caller_number: str
    answered_by: str
    state: CallState
    has_transcript: bool
    no_speech: bool


class CallListItem(CallSummary):
    passage: Passage | None


class CallList(BaseModel):
    calls: list[CallListItem]
    next_cursor: str | None


class CallDetail(CallSummary):
    queue_label: str | None  # Ravon's name for the queue, when the worker has read the list
    auto_queued: bool
    failure_reason: str | None
    transcribed_at: str | None
    language: str | None
    model: str | None


class Segment(BaseModel):
    idx: int
    start_s: float
    end_s: float
    text: str
    has_voiceprint: bool  # whether the admin can enroll this line for a person's voice


class Transcript(BaseModel):
    call_id: int
    language: str
    model: str
    transcribed_at: str
    no_speech: bool
    segments: list[Segment]


@router.get("")
def list_calls(  # noqa: PLR0913, PLR0917 - one parameter per filter
    conn: Db,
    state: CallState | None = None,
    since: Annotated[
        AwareDatetime | None,
        Query(description="Started at or after this moment, ISO 8601 with a time zone"),
    ] = None,
    start: Annotated[date | None, Query(alias="from", description="First day, store time")] = None,
    end: Annotated[date | None, Query(alias="to", description="Last day, store time")] = None,
    q: Annotated[str | None, Query(description="Words said in the call")] = None,
    number: Annotated[str | None, Query(description="Caller number, any punctuation")] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CallList:
    """Calls newest first, filtered and searched, one page at a time."""
    where = browse.CallFilter(state=state, since=since, start=start, end=end, text=q, number=number)
    try:
        page = browse.list_calls(
            conn, where, zone=Settings(conn).get(TIME_ZONE), limit=limit, cursor=cursor
        )
    except browse.BadCursor as error:
        raise ApiError(422, "invalid_cursor", str(error)) from None
    return CallList.model_validate({"calls": page.calls, "next_cursor": page.next_cursor})


@router.get("/{call_id}")
def get_call(call_id: int, conn: Db) -> CallDetail:
    found = browse.call_detail(conn, call_id)
    if found is None:
        raise ApiError(404, "call_not_found", f"No call {call_id} is listed.")
    return CallDetail.model_validate(found)


@router.get("/{call_id}/transcript")
def get_transcript(call_id: int, conn: Db) -> Transcript:
    found = browse.transcript(conn, call_id)
    if found is None:
        if browse.call_detail(conn, call_id) is None:
            raise ApiError(404, "call_not_found", f"No call {call_id} is listed.")
        raise ApiError(404, "no_transcript", "This call hasn't been transcribed yet.")
    return Transcript.model_validate(found)


@router.get(
    "/{call_id}/audio",
    response_class=Response,
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "The recording (MP3)."},
        502: {"description": "Ravon could not supply the recording."},
    },
)
def get_audio(call_id: int, conn: Db, ravon: Ravon) -> Response:
    """The call's recording, fetched from Ravon now and never stored.

    The one GET endpoint that sends a request to Ravon (the documented exception to
    "reads have no side effects"): one read-only recording download per call.
    """
    if browse.call_detail(conn, call_id) is None:
        raise ApiError(404, "call_not_found", f"No call {call_id} is listed.")
    try:
        audio = ravon.fetch(conn, call_id)
    except LoginRejected:
        raise ApiError(
            502, "ravon_login_failed", "Ravon refused the login, so the recording can't be fetched."
        ) from None
    except NoCredentials:
        raise ApiError(
            502, "ravon_no_credentials", "Ravon login details are missing, so it can't be played."
        ) from None
    except RavonError, ReadOnlyViolation:
        raise ApiError(
            502, "ravon_unavailable", "The recording can't be fetched from Ravon right now."
        ) from None
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


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
