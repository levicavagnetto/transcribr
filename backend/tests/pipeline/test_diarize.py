from pathlib import Path

import numpy as np
import pytest

from transcribr.pipeline.audio import decode
from transcribr.pipeline.diarize import Diarizer, Turn, label_segments
from transcribr.pipeline.transcribe import Segment, Transcriber, Word

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "audio"
MODELS = Path(__file__).resolve().parents[2] / "models"


def seg(start: float, end: float, *words: tuple[float, float, str]) -> Segment:
    return Segment(start, end, " ".join(w[2] for w in words), tuple(Word(*w) for w in words))


def test_each_segment_goes_to_the_speaker_it_overlaps_most() -> None:
    turns = [Turn(0.0, 4.0, 7), Turn(4.5, 9.0, 3)]
    segments = [
        seg(0.0, 3.5, (0.0, 1.0, "Thanks"), (1.0, 3.5, "calling.")),
        seg(4.6, 8.0, (4.6, 6.0, "Hi"), (6.0, 8.0, "there.")),
    ]
    labeled = label_segments(segments, turns)
    assert [(s.speaker, s.text) for s in labeled] == [
        ("Speaker 1", "Thanks calling."),
        ("Speaker 2", "Hi there."),
    ]


def test_a_segment_spanning_a_speaker_change_is_split_at_the_words() -> None:
    turns = [Turn(0.0, 2.0, 0), Turn(2.0, 5.0, 1)]
    labeled = label_segments(
        [
            seg(
                0.0,
                4.5,
                (0.1, 0.9, "this"),
                (1.0, 1.8, "is"),
                (2.2, 3.0, "hello"),
                (3.1, 4.5, "yes"),
            )
        ],
        turns,
    )
    assert [(s.speaker, s.text, s.start, s.end) for s in labeled] == [
        ("Speaker 1", "this is", 0.1, 1.8),
        ("Speaker 2", "hello yes", 2.2, 4.5),
    ]


def test_labels_follow_order_of_first_appearance() -> None:
    turns = [Turn(0.0, 2.0, 5), Turn(2.0, 4.0, 2), Turn(4.0, 6.0, 5)]
    labeled = label_segments(
        [seg(0, 2, (0, 2, "a")), seg(2, 4, (2, 4, "b")), seg(4, 6, (4, 6, "c"))], turns
    )
    assert [s.speaker for s in labeled] == ["Speaker 1", "Speaker 2", "Speaker 1"]


def test_words_outside_every_turn_go_to_the_nearest_turn() -> None:
    turns = [Turn(0.0, 1.0, 0), Turn(5.0, 6.0, 1)]
    labeled = label_segments(
        [seg(0.0, 1.0, (0.0, 1.0, "early")), seg(4.0, 4.5, (4.0, 4.5, "late"))], turns
    )
    assert [s.speaker for s in labeled] == [
        "Speaker 1",
        "Speaker 2",
    ]  # 4.25 s is nearer 5.0 than 1.0


def test_no_turns_puts_everything_on_one_speaker() -> None:
    labeled = label_segments([seg(0, 1, (0, 1, "hello"))], [])
    assert [s.speaker for s in labeled] == ["Speaker 1"]


requires_models = pytest.mark.skipif(
    not (MODELS / "sherpa-onnx" / "embedding.onnx").exists(),
    reason="run `uv run transcribr fetch-models --dest models` first",
)


@pytest.mark.model
@requires_models
def test_the_two_voice_dialogue_has_two_speakers_with_fingerprints() -> None:
    audio = decode((FIXTURES / "two-voices.mp3").read_bytes())
    transcript = Transcriber(MODELS).transcribe(audio)
    result = Diarizer(MODELS).diarize(audio, transcript)

    assert set(result.speakers) == {"Speaker 1", "Speaker 2"}
    by_speaker: dict[str, str] = {}
    for s in result.segments:
        by_speaker[s.speaker] = by_speaker.get(s.speaker, "") + " " + s.text
    assert "Nolan" in by_speaker["Speaker 1"]
    assert "lift kit" in by_speaker["Speaker 2"]

    one, two = result.speakers["Speaker 1"], result.speakers["Speaker 2"]
    assert one.fingerprint is not None and two.fingerprint is not None
    assert one.seconds > 3 and two.seconds > 3
    assert abs(float(np.linalg.norm(one.fingerprint)) - 1.0) < 1e-3
    # Measured on this clip: same voice 0.85-0.94 per turn, different voices 0.60-0.69.
    assert float(np.dot(one.fingerprint, two.fingerprint)) < 0.8


@pytest.mark.model
@requires_models
def test_silence_has_no_speakers() -> None:
    audio = decode((FIXTURES / "silence.mp3").read_bytes())
    transcript = Transcriber(MODELS).transcribe(audio)
    result = Diarizer(MODELS).diarize(audio, transcript)
    assert result.speakers == {}
    assert result.segments == ()
