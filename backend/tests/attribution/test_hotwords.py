import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from transcribr.attribution.profiles import Profiles
from transcribr.pipeline.audio import Samples
from transcribr.pipeline.process import ModelPipeline
from transcribr.pipeline.transcribe import Transcriber

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
MODELS = Path(__file__).resolve().parents[2] / "models"
SILENCE = (FIXTURES / "silence.mp3").read_bytes()


class HearsNothing:
    """A speech engine that records its options and finds no speech."""

    def __init__(self) -> None:
        self.hotwords: list[str | None] = []

    def transcribe(self, audio: Samples, **options: Any) -> tuple[list[Any], Any]:
        self.hotwords.append(options["hotwords"])
        return [], SimpleNamespace(language="en")


def test_the_current_name_variants_reach_the_engine_before_each_call(
    conn: sqlite3.Connection,
) -> None:
    engine = HearsNothing()
    profiles = Profiles(conn)
    pipeline = ModelPipeline(
        MODELS, hotwords=profiles.hotwords, transcriber=Transcriber(MODELS, engine=engine)
    )

    pipeline.run(SILENCE)
    nolan = profiles.create("Nolan", ["Nolan", "Nolen"])
    profiles.create("Dana", ["Dana", "Nolan"])
    pipeline.run(SILENCE)
    profiles.update(nolan.id, "Nolan", ["Nolan"])
    pipeline.run(SILENCE)

    assert engine.hotwords == [None, "Nolan Nolen Dana", "Dana Nolan"]


@pytest.mark.model
@pytest.mark.skipif(
    not (MODELS / "faster-whisper-small.en" / "model.bin").exists(),
    reason="run `uv run transcribr fetch-models --dest models` first",
)
def test_a_configured_name_is_spelled_as_configured(conn: sqlite3.Connection) -> None:
    audio = (FIXTURES / "two-voices.mp3").read_bytes()
    profiles = Profiles(conn)
    pipeline = ModelPipeline(MODELS, hotwords=profiles.hotwords)

    def names() -> list[str]:
        return re.findall(r"\bNol\w+", " ".join(line.text for line in pipeline.run(audio).segments))

    assert names() == ["Nolan"]  # how the model spells it unaided
    profiles.create("Nolen", ["Nolen"])
    assert names() == ["Nolen"]
