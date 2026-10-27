"""Open: the people the call list can be filtered by. Names and counts only."""

from fastapi import APIRouter
from pydantic import BaseModel

from transcribr.api.deps import Db
from transcribr.store import browse

router = APIRouter(prefix="/api/v1/people", tags=["people"])


class Person(BaseModel):
    id: int
    display_name: str
    calls: int  # attributed calls, Confident or Maybe
    maybe_calls: int


class People(BaseModel):
    people: list[Person]
    maybe_calls: int  # calls with at least one Maybe
    unassigned_calls: int  # transcribed calls nobody is attributed to


@router.get("")
def list_people(conn: Db) -> People:
    return People.model_validate(browse.people_counts(conn))
