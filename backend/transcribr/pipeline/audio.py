"""Decoding a recording's MP3 bytes in memory to 16 kHz mono float32 samples."""

import io

import av
import numpy as np
import numpy.typing as npt
from av.error import FFmpegError

SAMPLE_RATE = 16000

Samples = npt.NDArray[np.float32]


class AudioError(Exception):
    """The recording could not be decoded."""


def decode(data: bytes) -> Samples:
    """Decode audio bytes (any format PyAV reads) without touching the disk."""
    if not data:
        raise AudioError("the recording is empty")
    resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
    chunks: list[Samples] = []
    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                raise AudioError("the recording has no audio stream")
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1).astype(np.float32, copy=False))
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().reshape(-1).astype(np.float32, copy=False))
    except FFmpegError as error:
        raise AudioError(f"could not decode the recording: {error}") from error
    if not chunks:
        raise AudioError("the recording has no audio frames")
    return np.concatenate(chunks)
