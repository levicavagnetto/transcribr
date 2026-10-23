"""Keeping passwords and session cookies out of every log line."""

import logging
import re
import threading
from urllib.parse import quote, quote_plus

MASK = "[redacted]"
_MIN_SECRET_LENGTH = 6

_lock = threading.Lock()
_secrets: set[str] = set()

_PATTERNS = [
    # Form or query fields: password=..., pass=..., pwd=...
    (re.compile(r"(?i)\b(password|passwd|pass|pwd)=([^&\s'\"]+)"), rf"\1={MASK}"),
    # Header values: Cookie: ..., Set-Cookie: ..., also inside dict reprs.
    (re.compile(r"(?i)\b((?:set-)?cookie)(['\"]?\s*:\s*['\"]?)([^'\"\n]+)"), rf"\1\2{MASK}"),
    # Ravon's session cookies wherever they appear.
    (re.compile(r"(?i)\b(JSESSIONID|session)=([^;\s'\"&,]+)"), rf"\1={MASK}"),
]


def register_secret(value: str) -> None:
    """Mask this exact value (and its URL-encoded forms) in all future log output."""
    if len(value) < _MIN_SECRET_LENGTH:
        return
    with _lock:
        _secrets.update({value, quote(value, safe=""), quote_plus(value)})


def redact(text: str) -> str:
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, MASK)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    """A formatter whose whole output, tracebacks included, passes through `redact`."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
