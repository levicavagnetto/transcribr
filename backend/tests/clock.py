from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

EPOCH = datetime(2026, 10, 22, 14, 0, 0, tzinfo=UTC)  # 09:00 in the store's time zone


@dataclass
class FakeClock:
    """A clock that only moves when told to; `sleep` advances it and records the wait.

    `monotonic()` and `utcnow()` move together, so pacing and wall-clock logic agree.
    """

    now: float = 1000.0
    start: datetime = EPOCH
    sleeps: list[float] = field(default_factory=list[float])

    def monotonic(self) -> float:
        return self.now

    def utcnow(self) -> datetime:
        return self.start + timedelta(seconds=self.now - 1000.0)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
