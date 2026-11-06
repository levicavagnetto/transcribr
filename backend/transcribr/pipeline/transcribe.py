"""Speech to text with faster-whisper on the CPU (design D7)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from transcribr.models import WHISPER_DIR, WHISPER_MODEL_NAME
from transcribr.pipeline.audio import Samples


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Transcript:
    language: str
    model: str
    segments: tuple[Segment, ...]

    @property
    def no_speech(self) -> bool:
        return not any(s.text.strip() for s in self.segments)


class Engine(Protocol):
    """The part of faster_whisper.WhisperModel we use (a stand-in in unit tests)."""

    def transcribe(self, audio: Samples, **options: Any) -> tuple[Iterable[Any], Any]: ...


def _load_engine(models_dir: Path) -> Engine:
    # Untyped library; heavy, so imported only when transcribing.
    from faster_whisper import WhisperModel  # noqa: PLC0415  # pyright: ignore[reportMissingTypeStubs]

    model = WhisperModel(str(models_dir / WHISPER_DIR), device="cpu", compute_type="int8")
    return cast(Engine, model)


class Transcriber:
    def __init__(self, models_dir: Path, *, engine: Engine | None = None) -> None:
        self._engine = engine or _load_engine(models_dir)

    def transcribe(self, audio: Samples, *, hotwords: Sequence[str] = ()) -> Transcript:
        raw_segments, info = self._engine.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,
            hotwords=" ".join(hotwords) if hotwords else None,
        )
        segments = tuple(
            Segment(
                start=float(s.start),
                end=float(s.end),
                text=str(s.text).strip(),
                words=tuple(
                    Word(float(w.start), float(w.end), str(w.word).strip()) for w in (s.words or ())
                ),
            )
            for s in raw_segments
        )
        return Transcript(language=str(info.language), model=WHISPER_MODEL_NAME, segments=segments)
