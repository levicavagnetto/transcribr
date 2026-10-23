from dataclasses import dataclass, field


@dataclass
class FakeClock:
    """A monotonic clock that only moves when told to; `sleep` advances it and records the wait."""

    now: float = 1000.0
    sleeps: list[float] = field(default_factory=list[float])

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds
