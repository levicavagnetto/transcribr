from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from transcribr.pipeline.audio import Samples, decode
from transcribr.pipeline.transcribe import Transcriber

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
MODELS = Path(__file__).resolve().parents[2] / "models"


class StandInEngine:
    def __init__(self) -> None:
        self.options: dict[str, Any] = {}

    def transcribe(self, audio: Samples, **options: Any) -> tuple[list[Any], Any]:
        self.options = options
        word = SimpleNamespace(start=0.1, end=0.4, word=" Nolan")
        segment = SimpleNamespace(start=0.0, end=1.0, text=" this is Nolan ", words=[word])
        return [segment], SimpleNamespace(language="en")


def test_options_and_hotwords_reach_the_engine() -> None:
    engine = StandInEngine()
    result = Transcriber(MODELS, engine=engine).transcribe(
        np.zeros(16000, np.float32), hotwords=["Nolan", "Nolen"]
    )
    assert engine.options["hotwords"] == "Nolan Nolen"
    assert engine.options["language"] == "en"
    assert engine.options["vad_filter"] is True
    assert engine.options["word_timestamps"] is True
    assert result.segments[0].text == "this is Nolan"
    assert result.segments[0].words[0].text == "Nolan"
    assert result.model == "small.en"
    assert not result.no_speech


def test_no_hotwords_means_none_in_this_change() -> None:
    engine = StandInEngine()
    Transcriber(MODELS, engine=engine).transcribe(np.zeros(16000, np.float32))
    assert engine.options["hotwords"] is None


requires_models = pytest.mark.skipif(
    not (MODELS / "faster-whisper-small.en" / "model.bin").exists(),
    reason="run `uv run transcribr fetch-models --dest models` first",
)


@pytest.mark.model
@requires_models
def test_the_real_model_transcribes_the_dialogue() -> None:
    transcript = Transcriber(MODELS).transcribe(decode((FIXTURES / "two-voices.mp3").read_bytes()))
    text = " ".join(s.text for s in transcript.segments).lower()
    assert transcript.language == "en"
    # Without hints the model writes "Tire Pro's" and "Silver Rado"; the meaning survives.
    for phrase in ("tire pro", "nolan", "silver", "lift kit", "stock wheels", "call you back"):
        assert phrase in text, phrase
    words = [w for s in transcript.segments for w in s.words]
    assert words
    assert all(0 <= w.start <= w.end for w in words)


@pytest.mark.model
@requires_models
def test_the_real_model_finds_no_speech_in_silence() -> None:
    transcript = Transcriber(MODELS).transcribe(decode((FIXTURES / "silence.mp3").read_bytes()))
    assert transcript.no_speech


@pytest.mark.model
@requires_models
def test_hotwords_fix_brand_and_vehicle_names() -> None:
    audio = decode((FIXTURES / "two-voices.mp3").read_bytes())
    transcript = Transcriber(MODELS).transcribe(audio, hotwords=["Tire Pros", "Silverado", "Nolan"])
    text = " ".join(s.text for s in transcript.segments)
    assert "Tire Pros" in text
    assert "Silverado" in text
