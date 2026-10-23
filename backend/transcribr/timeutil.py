"""UTC timestamps as stored in the database: ISO 8601 with a Z, to the second."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def from_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def local_to_utc(local: datetime, zone: str) -> datetime:
    """A store wall-clock time (naive) as an aware UTC time."""
    return local.replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)


def utc_to_local(moment: datetime, zone: str) -> datetime:
    """An aware time as naive store wall-clock time, the form Ravon's search uses."""
    return moment.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
