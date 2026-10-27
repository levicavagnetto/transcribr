"""The automatic attribution rules (design D4), as a pure function.

- Strong voice: Confident.
- Name with strong or weak voice: Confident.
- Name with no voice profile yet, or a call too short to tell by voice: Confident.
- Name where the voice profile has no voice match, even weak: Maybe.
- Weak voice alone: Maybe.
A profile with a manual decision on the call is left out: manual decisions always win.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from transcribr.attribution.names import NameHit
from transcribr.attribution.voice import band


@dataclass(frozen=True)
class Evidence:
    name: NameHit | None
    voice_usable: bool  # the profile has enough enrolled speech for voice matching
    presence: float | None  # the call's presence score; None if unusable or too little speech


@dataclass(frozen=True)
class Decision:
    profile_id: int
    status: str  # 'confident' or 'maybe'
    method: str  # 'name', 'voice' or 'name+voice'
    name: NameHit | None
    voice_score: float | None


def decide(
    evidence: Mapping[int, Evidence],
    *,
    low: float,
    high: float,
    manual: Collection[int] = (),
) -> list[Decision]:
    """Automatic attributions for one call, from each profile's evidence."""
    decisions: list[Decision] = []
    for profile_id, found in sorted(evidence.items()):
        if profile_id in manual:
            continue
        voice = band(found.presence, low, high) if found.voice_usable else None
        score = found.presence if found.voice_usable else None
        if found.name is not None:
            if voice is not None:
                status, method = "confident", "name+voice"
            elif not found.voice_usable or found.presence is None:
                status, method = "confident", "name"
            else:
                status, method = "maybe", "name"
        elif voice == "strong":
            status, method = "confident", "voice"
        elif voice == "weak":
            status, method = "maybe", "voice"
        else:
            continue
        decisions.append(Decision(profile_id, status, method, found.name, score))
    return decisions
