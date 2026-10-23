"""Who spoke when, and one voice fingerprint per speaker, with sherpa-onnx (design D8)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from transcribr.models import EMBEDDING_MODEL, SEGMENTATION_MODEL
from transcribr.pipeline.audio import SAMPLE_RATE, Samples
from transcribr.pipeline.transcribe import Segment, Transcript, Word

# Provisional (larger = fewer speakers). 0.42-0.44 gives the right count on both test sources:
# a real 2-person call (0.35-0.40 split the staff voice off, 0.5+ merged both) and the synthetic
# clip (0.45+ merged it). Calibrated on more real calls in add-call-attribution.
CLUSTERING_THRESHOLD = 0.43
MIN_TURN_FOR_FINGERPRINT = 1.5  # seconds
MIN_SPEECH_FOR_FINGERPRINT = 3.0  # seconds


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    speaker: int


@dataclass(frozen=True)
class LabeledSegment:
    start: float
    end: float
    speaker: str
    text: str
    words: tuple[Word, ...]


@dataclass(frozen=True)
class SpeakerInfo:
    label: str
    seconds: float
    fingerprint: Samples | None  # L2-normalized; None when too little clean speech


@dataclass(frozen=True)
class Diarized:
    segments: tuple[LabeledSegment, ...]
    speakers: dict[str, SpeakerInfo]


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _speaker_at(start: float, end: float, turns: Sequence[Turn]) -> int | None:
    if not turns:
        return None
    best = max(turns, key=lambda t: _overlap(start, end, t.start, t.end))
    if _overlap(start, end, best.start, best.end) > 0:
        return best.speaker
    middle = (start + end) / 2
    return min(turns, key=lambda t: min(abs(middle - t.start), abs(middle - t.end))).speaker


def label_segments(segments: Sequence[Segment], turns: Sequence[Turn]) -> list[LabeledSegment]:
    """Give every transcript line a speaker, splitting lines where the speaker changes."""
    return _label(segments, turns)[0]


def _label(
    segments: Sequence[Segment], turns: Sequence[Turn]
) -> tuple[list[LabeledSegment], dict[int | None, str]]:
    """The labeled lines, and which sherpa cluster got which "Speaker N" label."""
    pieces: list[tuple[int | None, LabeledSegment]] = []
    for segment in segments:
        if not segment.words:
            speaker = _speaker_at(segment.start, segment.end, turns)
            pieces.append(
                (speaker, LabeledSegment(segment.start, segment.end, "", segment.text, ()))
            )
            continue
        run: list[Word] = []
        run_speaker: int | None = None
        for word in segment.words:
            speaker = _speaker_at(word.start, word.end, turns)
            if run and speaker != run_speaker:
                pieces.append((run_speaker, _piece(run)))
                run = []
            run.append(word)
            run_speaker = speaker
        pieces.append((run_speaker, _piece(run)))
    labels: dict[int | None, str] = {}
    for speaker, _ in pieces:
        labels.setdefault(speaker, f"Speaker {len(labels) + 1}")
    labeled = [
        LabeledSegment(p.start, p.end, labels[speaker], p.text, p.words) for speaker, p in pieces
    ]
    return labeled, labels


def _piece(words: list[Word]) -> LabeledSegment:
    return LabeledSegment(
        words[0].start, words[-1].end, "", " ".join(w.text for w in words), tuple(words)
    )


class Diarizer:
    def __init__(self, models_dir: Path, *, threshold: float = CLUSTERING_THRESHOLD) -> None:
        # Untyped library; heavy, so imported only when processing. Its objects are kept as Any.
        import sherpa_onnx as _sherpa_onnx  # noqa: PLC0415  # pyright: ignore[reportMissingTypeStubs]

        sherpa_onnx: Any = _sherpa_onnx

        embedding = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(models_dir / EMBEDDING_MODEL)
        )
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(models_dir / SEGMENTATION_MODEL)
                )
            ),
            embedding=embedding,
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=threshold),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not config.validate():
            raise ValueError(f"speaker models are missing or invalid in {models_dir}")
        self._diarization: Any = sherpa_onnx.OfflineSpeakerDiarization(config)
        self._extractor: Any = sherpa_onnx.SpeakerEmbeddingExtractor(embedding)

    def diarize(self, audio: Samples, transcript: Transcript) -> Diarized:
        result: list[Any] = self._diarization.process(audio).sort_by_start_time()
        turns = [Turn(float(r.start), float(r.end), int(r.speaker)) for r in result]
        segments, labels = _label(transcript.segments, turns)
        speakers: dict[str, SpeakerInfo] = {}
        for cluster, label in labels.items():
            if cluster is None:  # no turns at all: no fingerprint to take
                speakers[label] = SpeakerInfo(label, 0.0, None)
                continue
            own = [t for t in turns if t.speaker == cluster]
            seconds = sum(t.end - t.start for t in own)
            speakers[label] = SpeakerInfo(label, seconds, self._fingerprint(audio, own))
        return Diarized(tuple(segments), speakers)

    def _fingerprint(self, audio: Samples, turns: Sequence[Turn]) -> Samples | None:
        usable = [t for t in turns if t.end - t.start >= MIN_TURN_FOR_FINGERPRINT]
        if sum(t.end - t.start for t in usable) < MIN_SPEECH_FOR_FINGERPRINT:
            return None
        vectors: list[Samples] = []
        for turn in usable:
            stream: Any = self._extractor.create_stream()
            chunk = audio[int(turn.start * SAMPLE_RATE) : int(turn.end * SAMPLE_RATE)]
            stream.accept_waveform(SAMPLE_RATE, chunk)
            stream.input_finished()
            vector: Samples = np.asarray(self._extractor.compute(stream), dtype=np.float32)
            vectors.append(vector / np.linalg.norm(vector))
        mean = np.mean(np.stack(vectors), axis=0).astype(np.float32)
        return mean / np.linalg.norm(mean)
