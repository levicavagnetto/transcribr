"""Name evidence: a profile's name variant said in the first 30 seconds of speech (design D2)."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

OPENING_SECONDS = 30.0  # from the first word, not from the start of the recording
MATCH_RATIO = 88.0  # rapidfuzz fuzz.ratio, 0-100

_NOT_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Lowercase, accents folded, punctuation removed, words separated by single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NOT_WORD.sub(" ", folded).strip()


@dataclass(frozen=True)
class Token:
    text: str  # normalized
    heard: str  # the transcript word it came from
    at_s: float


@dataclass(frozen=True)
class NameHit:
    variant: str
    heard: str  # the transcript words that matched
    at_s: float


def opening(words: Sequence[tuple[float, str]]) -> list[Token]:
    """The normalized tokens of the (start, word) pairs said in the opening of a call."""
    if not words:
        return []
    cutoff = min(start for start, _ in words) + OPENING_SECONDS
    tokens: list[Token] = []
    for start, word in sorted(words, key=lambda w: w[0]):
        if start >= cutoff:
            break
        tokens.extend(Token(part, word.strip(), start) for part in normalize(word).split())
    return tokens


def find_name(tokens: Sequence[Token], variants: Sequence[str]) -> NameHit | None:
    """The earliest place in the opening where one of the variants was said, if any."""
    best: NameHit | None = None
    for variant in variants:
        wanted = normalize(variant)
        size = len(wanted.split())
        if size == 0:
            continue
        for at in range(len(tokens) - size + 1):
            window = tokens[at : at + size]
            if best is not None and window[0].at_s >= best.at_s:
                break
            if fuzz.ratio(" ".join(t.text for t in window), wanted) >= MATCH_RATIO:
                heard = " ".join(dict.fromkeys(t.heard for t in window))
                best = NameHit(variant, heard, window[0].at_s)
                break
    return best
