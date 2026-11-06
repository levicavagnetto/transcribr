import tempfile
from pathlib import Path

import numpy as np
import pytest

from transcribr.pipeline.audio import AudioError, decode

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"


def test_decodes_ravon_style_mp3_to_16k_mono_float() -> None:
    audio = decode((FIXTURES / "two-voices.mp3").read_bytes())
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert 36.0 < len(audio) / 16000 < 38.0
    assert 0.01 < float(np.abs(audio).max()) <= 1.0


def test_silence_decodes_to_near_zero() -> None:
    audio = decode((FIXTURES / "silence.mp3").read_bytes())
    assert 2.5 < len(audio) / 16000 < 3.5
    assert float(np.abs(audio).max()) < 0.01


def test_garbage_is_an_audio_error() -> None:
    with pytest.raises(AudioError):
        decode(b"this is not an mp3 file at all" * 10)


def test_empty_is_an_audio_error() -> None:
    with pytest.raises(AudioError):
        decode(b"")


def test_decoding_writes_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    decode((FIXTURES / "two-voices.mp3").read_bytes())
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
