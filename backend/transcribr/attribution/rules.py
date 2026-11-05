"""The automatic attribution rule (design D4), as a pure function.

A profile whose name is heard in the opening is a Maybe, method name: the name alone can't tell
"this is Nolan" from "is Nolan there?", so only a person's decision makes a call Confident.
A profile with a manual decision on the call is left out: manual decisions always win.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from transcribr.attribution.names import NameHit


@dataclass(frozen=True)
class Decision:
    profile_id: int
    status: str  # always 'maybe' for automatic rows
    method: str  # always 'name'
    name: NameHit


def decide(names: Mapping[int, NameHit | None], *, manual: Collection[int] = ()) -> list[Decision]:
    """Automatic attributions for one call, from each profile's name hit."""
    return [
        Decision(profile_id, "maybe", "name", hit)
        for profile_id, hit in sorted(names.items())
        if hit is not None and profile_id not in manual
    ]
