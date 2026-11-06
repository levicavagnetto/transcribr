"""Admin only: people profiles and their name variants (add-call-attribution design D7)."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from transcribr.api.deps import Db, Now, profile_error, require_admin
from transcribr.attribution.profiles import Profile, ProfileError, Profiles

router = APIRouter(
    prefix="/api/v1/admin/profiles", tags=["admin"], dependencies=[Depends(require_admin)]
)


class ProfileIn(BaseModel):
    display_name: str
    variants: list[str]


class Found(BaseModel):
    """How this person's calls were found (Confident and Maybe)."""

    name: int
    manual: int
    maybe: int


class ProfileOut(BaseModel):
    id: int
    display_name: str
    variants: list[str]
    created_at: str
    found: Found


class ProfileList(BaseModel):
    profiles: list[ProfileOut]


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
    return Found(name=counts.get("name", 0), manual=counts.get("manual", 0), maybe=maybe)


def _out(conn: Db, profile: Profile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        display_name=profile.display_name,
        variants=list(profile.variants),
        created_at=profile.created_at,
        found=_found(conn, profile.id),
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
    """Delete the person and every attribution to them."""
    try:
        Profiles(conn, now=lambda: now).delete(profile_id)
    except ProfileError as error:
        raise profile_error(error) from None
    return {"deleted": True}
