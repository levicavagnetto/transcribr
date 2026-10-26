import hashlib
from pathlib import Path

import httpx
import pytest

from transcribr.models import MANIFEST, ModelError, ModelFile, fetch_models, verify_models

GOOD = b"model bytes " * 100


def file(name: str, content: bytes = GOOD) -> ModelFile:
    return ModelFile(
        dest=f"whisper/{name}",
        url=f"https://models.example/{name}",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def serve(content: bytes) -> tuple[httpx.MockTransport, list[str]]:
    hits: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200, content=content)

    return httpx.MockTransport(handle), hits


def test_downloads_verifies_and_places_files(tmp_path: Path) -> None:
    transport, _ = serve(GOOD)
    fetch_models(tmp_path, [file("model.bin")], transport=transport)
    assert (tmp_path / "whisper" / "model.bin").read_bytes() == GOOD
    assert not list(tmp_path.rglob("*.part"))


def test_verified_files_are_not_downloaded_again(tmp_path: Path) -> None:
    transport, hits = serve(GOOD)
    fetch_models(tmp_path, [file("model.bin")], transport=transport)
    fetch_models(tmp_path, [file("model.bin")], transport=transport)
    assert len(hits) == 1


def test_a_checksum_mismatch_is_rejected_and_nothing_is_placed(tmp_path: Path) -> None:
    transport, _ = serve(b"tampered" + GOOD[8:])
    with pytest.raises(ModelError, match="SHA-256"):
        fetch_models(tmp_path, [file("model.bin")], transport=transport)
    assert not (tmp_path / "whisper" / "model.bin").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_a_wrong_size_is_rejected(tmp_path: Path) -> None:
    transport, _ = serve(GOOD[:-1])
    with pytest.raises(ModelError, match="size"):
        fetch_models(tmp_path, [file("model.bin")], transport=transport)


def test_verify_reports_missing_and_corrupt_files(tmp_path: Path) -> None:
    good, bad = file("a.bin"), file("b.bin")
    (tmp_path / "whisper").mkdir()
    (tmp_path / "whisper" / "a.bin").write_bytes(GOOD)
    (tmp_path / "whisper" / "b.bin").write_bytes(b"x" * len(GOOD))
    problems = verify_models(tmp_path, [good, bad, file("c.bin")])
    assert problems == ["whisper/b.bin: SHA-256 mismatch", "whisper/c.bin: missing"]


def test_the_real_manifest_pins_revisions_and_hashes() -> None:
    dests = {f.dest for f in MANIFEST}
    assert dests == {
        "faster-whisper-small.en/config.json",
        "faster-whisper-small.en/model.bin",
        "faster-whisper-small.en/tokenizer.json",
        "faster-whisper-small.en/vocabulary.txt",
        "sherpa-onnx/embedding.onnx",
    }
    for f in MANIFEST:
        assert len(f.sha256) == 64
        assert f.size > 0
        assert "/resolve/main/" not in f.url  # pinned to a commit, not a moving branch
