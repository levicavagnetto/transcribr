"""The speech and speaker-embedding models: pinned downloads, checked by size and SHA-256.

The Docker image runs `transcribr fetch-models` at build time, so a running instance never
downloads anything. For development, run it once into `backend/models` (git-ignored).
"""

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

WHISPER_DIR = "faster-whisper-small.en"
WHISPER_MODEL_NAME = "small.en"
EMBEDDING_MODEL = "sherpa-onnx/embedding.onnx"

_WHISPER = (
    "https://huggingface.co/Systran/faster-whisper-small.en/resolve/"
    "d1d751a5f8271d482d14ca55d9e2deeebbae577f"
)
_EMBEDDING = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
    "wespeaker_en_voxceleb_resnet34_LM.onnx"
)


class ModelError(Exception):
    pass


@dataclass(frozen=True)
class ModelFile:
    dest: str
    url: str
    size: int
    sha256: str


MANIFEST: tuple[ModelFile, ...] = (
    ModelFile(
        f"{WHISPER_DIR}/config.json",
        f"{_WHISPER}/config.json",
        2657,
        "666a9605530ac1f61fa8177f3702b4dacec9966749e42610839fcc32661d5fae",
    ),
    ModelFile(
        f"{WHISPER_DIR}/model.bin",
        f"{_WHISPER}/model.bin",
        483545366,
        "62b2a45b05ee59acb4a5341b33ee35e041395d378d418a18acfe4c9e768ee37a",
    ),
    ModelFile(
        f"{WHISPER_DIR}/tokenizer.json",
        f"{_WHISPER}/tokenizer.json",
        2128466,
        "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
    ),
    ModelFile(
        f"{WHISPER_DIR}/vocabulary.txt",
        f"{_WHISPER}/vocabulary.txt",
        422309,
        "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
    ),
    ModelFile(
        EMBEDDING_MODEL,
        _EMBEDDING,
        26530550,
        "e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012",
    ),
)

_CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _problem(root: Path, model: ModelFile) -> str | None:
    path = root / model.dest
    if not path.is_file():
        return "missing"
    if path.stat().st_size != model.size:
        return "size mismatch"
    if _sha256(path) != model.sha256:
        return "SHA-256 mismatch"
    return None


def verify_models(root: Path, manifest: Sequence[ModelFile] = MANIFEST) -> list[str]:
    """Problems with the installed models, as 'path: reason'; empty when all are good."""
    return [f"{m.dest}: {p}" for m in manifest if (p := _problem(root, m)) is not None]


def fetch_models(
    root: Path,
    manifest: Sequence[ModelFile] = MANIFEST,
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Download every missing or damaged file; each is verified before it is put in place."""
    with httpx.Client(transport=transport, follow_redirects=True, timeout=120.0) as client:
        for model in manifest:
            if _problem(root, model) is None:
                log.info("%s is already present and verified", model.dest)
                continue
            target = root / model.dest
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            log.info("downloading %s", model.dest)
            try:
                with client.stream("GET", model.url) as response, part.open("wb") as out:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(_CHUNK):
                        out.write(chunk)
                if part.stat().st_size != model.size:
                    raise ModelError(f"{model.dest}: size {part.stat().st_size} != {model.size}")
                if _sha256(part) != model.sha256:
                    raise ModelError(f"{model.dest}: SHA-256 does not match the pinned value")
                part.replace(target)
            except (httpx.HTTPError, OSError) as error:
                raise ModelError(f"{model.dest}: download failed: {error}") from error
            finally:
                part.unlink(missing_ok=True)
