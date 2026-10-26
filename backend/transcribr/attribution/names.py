"""Name text as matching compares it (design D2)."""

import re
import unicodedata

_NOT_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Lowercase, accents folded, punctuation removed, words separated by single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NOT_WORD.sub(" ", folded).strip()
