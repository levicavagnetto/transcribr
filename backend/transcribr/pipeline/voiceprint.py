"""One voiceprint per transcript line, with sherpa-onnx's speaker-embedding model.

No speaker separation runs: lines are not assigned to speakers (add-call-attribution D0, D1).
A line's voiceprint is only ever compared with staff voice profiles, never named.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from transcribr.models import EMBEDDING_MODEL
from transcribr.pipeline.audio import SAMPLE_RATE, Samples
from transcribr.pipeline.transcribe import Segment, Word

MIN_LINE_SECONDS = 1.0  # shorter lines give unreliable embeddings, so they get no voiceprint


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str
    words: tuple[Word, ...]
    voiceprint: Samples | None  # L2-normalized float32; None for lines under MIN_LINE_SECONDS


def qualifies(start: float, end: float) -> bool:
    """Whether a line is long enough to get a voiceprint."""
    return end - start >= MIN_LINE_SECONDS


def voiceprint_lines(
    segments: Sequence[Segment], embed: Callable[[float, float], Samples]
) -> tuple[Line, ...]:
    """Each transcript segment as a line, with a voiceprint when it qualifies."""
    return tuple(
        Line(
            s.start,
            s.end,
            s.text,
            s.words,
            embed(s.start, s.end) if qualifies(s.start, s.end) else None,
        )
        for s in segments
    )


class Voiceprinter:
    def __init__(self, models_dir: Path) -> None:
        # Untyped library; heavy, so imported only when processing. Its objects are kept as Any.
        import sherpa_onnx as _sherpa_onnx  # noqa: PLC0415  # pyright: ignore[reportMissingTypeStubs]

        sherpa_onnx: Any = _sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(models_dir / EMBEDDING_MODEL)
        )
        if not config.validate():
            raise ValueError(f"speaker-embedding model is missing or invalid in {models_dir}")
        self._extractor: Any = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    def lines(self, audio: Samples, segments: Sequence[Segment]) -> tuple[Line, ...]:
        return voiceprint_lines(segments, lambda start, end: self.embed(audio, start, end))

    def embed(self, audio: Samples, start: float, end: float) -> Samples:
        stream: Any = self._extractor.create_stream()
        stream.accept_waveform(
            SAMPLE_RATE, audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]
        )
        stream.input_finished()
        vector: Samples = np.asarray(self._extractor.compute(stream), dtype=np.float32)
        return vector / np.linalg.norm(vector)
