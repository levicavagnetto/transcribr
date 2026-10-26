from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from transcribr.pipeline.audio import Samples
from transcribr.pipeline.process import ModelPipeline
from transcribr.pipeline.transcribe import Segment, Word
from transcribr.pipeline.voiceprint import MIN_LINE_SECONDS, Line, qualifies, voiceprint_lines

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
MODELS = Path(__file__).resolve().parents[2] / "models"


def seg(start: float, end: float, text: str) -> Segment:
    return Segment(start, end, text, (Word(start, end, text),))


def test_lines_of_one_second_or_more_qualify() -> None:
    assert MIN_LINE_SECONDS == 1.0
    assert qualifies(2.0, 3.0)
    assert qualifies(0.0, 12.5)
    assert not qualifies(2.0, 2.99)
    assert not qualifies(4.0, 4.0)


def test_only_qualifying_lines_are_embedded() -> None:
    asked: list[tuple[float, float]] = []

    def embed(start: float, end: float) -> Samples:
        asked.append((start, end))
        return np.full(4, 0.5, dtype=np.float32)

    lines = voiceprint_lines(
        [seg(0.0, 3.5, "this is Nolan"), seg(4.0, 4.6, "yes"), seg(5.0, 6.0, "a lift kit")], embed
    )
    assert asked == [(0.0, 3.5), (5.0, 6.0)]
    assert [(line.text, line.voiceprint is not None) for line in lines] == [
        ("this is Nolan", True),
        ("yes", False),
        ("a lift kit", True),
    ]
    assert lines[0].words == (Word(0.0, 3.5, "this is Nolan"),)


def test_lines_carry_no_speaker() -> None:
    assert "speaker" not in {f.name for f in fields(Line)}


requires_models = pytest.mark.skipif(
    not (MODELS / "sherpa-onnx" / "embedding.onnx").exists(),
    reason="run `uv run transcribr fetch-models --dest models` first",
)


@pytest.mark.model
@requires_models
def test_the_two_voice_dialogue_gets_one_voiceprint_per_qualifying_line() -> None:
    result = ModelPipeline(MODELS).run((FIXTURES / "two-voices.mp3").read_bytes())

    assert result.segments
    text = " ".join(line.text for line in result.segments)
    assert "Nolan" in text and "lift kit" in text
    for line in result.segments:
        assert not hasattr(line, "speaker")
        if qualifies(line.start, line.end):
            assert line.voiceprint is not None
            assert line.voiceprint.dtype == np.float32
            assert abs(float(np.linalg.norm(line.voiceprint)) - 1.0) < 1e-3
        else:
            assert line.voiceprint is None
    assert any(line.voiceprint is not None for line in result.segments)


@pytest.mark.model
@requires_models
def test_silence_has_no_lines() -> None:
    result = ModelPipeline(MODELS).run((FIXTURES / "silence.mp3").read_bytes())
    assert result.segments == ()
    assert result.no_speech
