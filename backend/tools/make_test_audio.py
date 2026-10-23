"""Make the synthetic test clips in tests/fixtures/audio (Windows only; the clips are committed).

Two built-in Windows text-to-speech voices act out a short shop call, so tests have two
distinct speakers without using anyone's real voice. The result is encoded like Ravon's
recordings: MP3, 8 kHz, mono, 64 kbps.

    uv run python tools/make_test_audio.py
"""

import io
import subprocess
import tempfile
import wave
from pathlib import Path

import av
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "audio"
STAFF = "Microsoft David Desktop"
CUSTOMER = "Microsoft Zira Desktop"
RATE = 16000
GAP_SECONDS = 0.6

DIALOGUE = [
    (STAFF, "Thanks for calling Tire Pros Stillwater, this is Nolan. How can I help you?"),
    (CUSTOMER, "Hi, I have a twenty nineteen Silverado, and I'm looking at a three inch lift kit."),
    (STAFF, "Sure. Do you want to keep the stock wheels, or are you thinking about new ones?"),
    (
        CUSTOMER,
        "I'd like to keep the stock wheels if I can. My budget is about two thousand dollars.",
    ),
    (STAFF, "Got it. Let me look up a couple of kits, and I will call you back tomorrow."),
    (CUSTOMER, "Perfect, thank you so much."),
]

_SPEAK = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({rate}, 'Sixteen', 'Mono')
$s.SelectVoice('{voice}')
$s.SetOutputToWaveFile('{path}', $format)
$s.Speak('{text}')
$s.Dispose()
"""


def speak(voice: str, text: str, folder: Path, index: int) -> np.ndarray:
    path = folder / f"line{index}.wav"
    script = _SPEAK.format(rate=RATE, voice=voice, path=path, text=text.replace("'", "''"))
    subprocess.run(  # noqa: S603 - fixed command, our own text
        ["powershell", "-NoProfile", "-Command", script],  # noqa: S607
        check=True,
    )
    with wave.open(str(path)) as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)


def encode_mp3(samples: np.ndarray, target: Path) -> None:
    """Encode 16 kHz int16 mono samples as an 8 kHz 64 kbps mono MP3, as Ravon serves them."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp3") as container:
        stream = container.add_stream("mp3", rate=8000, layout="mono")
        stream.bit_rate = 64000
        resampler = av.AudioResampler(format="s16p", layout="mono", rate=8000)
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = RATE
        for chunk in [*resampler.resample(frame), *resampler.resample(None)]:
            for packet in stream.encode(chunk):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    target.write_bytes(buffer.getvalue())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(RATE * GAP_SECONDS), dtype=np.int16)
    with tempfile.TemporaryDirectory() as folder:
        parts: list[np.ndarray] = []
        for index, (voice, text) in enumerate(DIALOGUE):
            parts.extend([speak(voice, text, Path(folder), index), gap])
    encode_mp3(np.concatenate(parts), OUT / "two-voices.mp3")
    encode_mp3(np.zeros(RATE * 3, dtype=np.int16), OUT / "silence.mp3")
    for clip in sorted(OUT.glob("*.mp3")):
        print(f"{clip.name}: {clip.stat().st_size} bytes")


if __name__ == "__main__":
    main()
