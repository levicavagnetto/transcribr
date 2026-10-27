"""Admin only: people profiles and voice enrollment (add-call-attribution design D7).

Voice data stays inside: responses give enrolled lines' times and seconds, never voiceprints
or centroids.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from transcribr.api.deps import Db, Now, profile_error, require_admin
from transcribr.attribution.profiles import Profile, ProfileError, Profiles
from transcribr.attribution.voice import VoiceProgress, VoiceSamples

router = APIRouter(
    prefix="/api/v1/admin/profiles", tags=["admin"], dependencies=[Depends(require_admin)]
)


class ProfileIn(BaseModel):
    display_name: str
    variants: list[str]


class Voice(BaseModel):
    calls: int
    seconds: float
    usable: bool  # enough enrolled speech for voice matching
    calls_needed: int  # how much more is needed before it is usable
    seconds_needed: float


class Found(BaseModel):
    """How this person's calls were found (Confident and Maybe)."""

    name: int
    voice: int
    name_and_voice: int
    manual: int
    maybe: int


class ProfileOut(BaseModel):
    id: int
    display_name: str
    variants: list[str]
    created_at: str
    voice: Voice
    found: Found


class ProfileList(BaseModel):
    profiles: list[ProfileOut]


class EnrolledLine(BaseModel):
    idx: int
    start_s: float
    end_s: float


class EnrolledCall(BaseModel):
    call_id: int
    start_local: str
    seconds: float
    lines: list[EnrolledLine]


class Samples(BaseModel):
    voice: Voice
    calls: list[EnrolledCall]


class SamplesIn(BaseModel):
    call_id: int
    lines: list[int]


def _voice(progress: VoiceProgress) -> Voice:
    return Voice(
        calls=progress.calls,
        seconds=progress.seconds,
        usable=progress.usable,
        calls_needed=progress.calls_needed,
        seconds_needed=progress.seconds_needed,
    )


def _found(conn: Db, profile_id: int) -> Found:
    counts: dict[str, Any] = {
        r["method"]: r["n"]
        for r in conn.execute(
            "SELECT method, count(*) AS n FROM attributions"
            " WHERE profile_id = ? AND status IN ('confident', 'maybe') GROUP BY method",
            (profile_id,),
        )
    }
    maybe: int = conn.execute(
        "SELECT count(*) FROM attributions WHERE profile_id = ? AND status = 'maybe'",
        (profile_id,),
    ).fetchone()[0]
    return Found(
        name=counts.get("name", 0),
        voice=counts.get("voice", 0),
        name_and_voice=counts.get("name+voice", 0),
        manual=counts.get("manual", 0),
        maybe=maybe,
    )


def _out(conn: Db, profile: Profile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        display_name=profile.display_name,
        variants=list(profile.variants),
        created_at=profile.created_at,
        voice=_voice(VoiceSamples(conn).progress(profile.id)),
        found=_found(conn, profile.id),
    )


def _samples(conn: Db, profile_id: int) -> Samples:
    samples = VoiceSamples(conn)
    return Samples(
        voice=_voice(samples.progress(profile_id)),
        calls=[
            EnrolledCall(
                call_id=c.call_id,
                start_local=c.start_local,
                seconds=c.seconds,
                lines=[EnrolledLine(idx=x.idx, start_s=x.start_s, end_s=x.end_s) for x in c.lines],
            )
            for c in samples.enrolled(profile_id)
        ],
    )


@router.get("")
def list_profiles(conn: Db) -> ProfileList:
    return ProfileList(profiles=[_out(conn, p) for p in Profiles(conn).everyone()])


@router.post("")
def create_profile(body: ProfileIn, conn: Db, now: Now) -> ProfileOut:
    try:
        profile = Profiles(conn, now=lambda: now).create(body.display_name, body.variants)
    except ProfileError as error:
        raise profile_error(error) from None
    return _out(conn, profile)


@router.get("/{profile_id}")
def get_profile(profile_id: int, conn: Db) -> ProfileOut:
    try:
        return _out(conn, Profiles(conn).get(profile_id))
    except ProfileError as error:
        raise profile_error(error) from None


@router.put("/{profile_id}")
def update_profile(profile_id: int, body: ProfileIn, conn: Db, now: Now) -> ProfileOut:
    """Rename the person and replace their name variants."""
    try:
        profile = Profiles(conn, now=lambda: now).update(
            profile_id, body.display_name, body.variants
        )
    except ProfileError as error:
        raise profile_error(error) from None
    return _out(conn, profile)


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, conn: Db, now: Now) -> dict[str, bool]:
    """Delete the person, their voice profile and every attribution to them."""
    try:
        Profiles(conn, now=lambda: now).delete(profile_id)
    except ProfileError as error:
        raise profile_error(error) from None
    return {"deleted": True}


@router.get("/{profile_id}/samples")
def list_samples(profile_id: int, conn: Db) -> Samples:
    """The person's enrolled lines, grouped by call, newest call first."""
    try:
        Profiles(conn).get(profile_id)
    except ProfileError as error:
        raise profile_error(error) from None
    return _samples(conn, profile_id)


@router.post("/{profile_id}/samples")
def add_samples(profile_id: int, body: SamplesIn, conn: Db, now: Now) -> Samples:
    """Enroll ticked lines of a transcribed call where only this person is talking."""
    try:
        VoiceSamples(conn, now=lambda: now).add(profile_id, body.call_id, body.lines)
    except ProfileError as error:
        raise profile_error(error) from None
    return _samples(conn, profile_id)


@router.delete("/{profile_id}/samples/{call_id}")
def remove_samples(profile_id: int, call_id: int, conn: Db, now: Now) -> Samples:
    """Take one call's enrolled lines out of the person's voice profile."""
    try:
        VoiceSamples(conn, now=lambda: now).remove_call(profile_id, call_id)
    except ProfileError as error:
        raise profile_error(error) from None
    return _samples(conn, profile_id)
