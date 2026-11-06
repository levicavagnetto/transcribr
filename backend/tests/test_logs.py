import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.test_redaction import PASSWORD, assert_no_secrets, log_records_carrying_secrets
from transcribr import logs
from transcribr.logs import setup_service_logging
from transcribr.redaction import register_secret


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_ours = logging.getLogger("transcribr").level
    yield
    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    logging.getLogger("transcribr").setLevel(saved_ours)


def flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_the_redaction_test_passes_through_stdout_and_the_file(tmp_path: Path) -> None:
    stdout = io.StringIO()
    log_file = setup_service_logging("web", tmp_path, stream=stdout)
    log_records_carrying_secrets(logging.getLogger("transcribr.test"))
    flush()

    assert log_file == tmp_path / "logs" / "web.log"
    for out in (stdout.getvalue(), log_file.read_text(encoding="utf-8")):
        assert_no_secrets(out)
        lines = out.splitlines()
        assert len(lines) == 5
        entries = [json.loads(line) for line in lines]
        assert {e["logger"] for e in entries} == {"transcribr.test"}
        assert entries[3]["level"] == "WARNING"
        assert "RuntimeError" in entries[4]["exception"]


def test_secrets_that_json_would_escape_are_still_redacted(tmp_path: Path) -> None:
    stdout = io.StringIO()
    setup_service_logging("worker", tmp_path, stream=stdout)
    tricky = 'quote"and\\backslash-' + PASSWORD
    register_secret(tricky)
    logging.getLogger("transcribr.test").warning("value %s", tricky)
    flush()
    assert json.loads(stdout.getvalue())["message"] == "value [redacted]"


def test_only_info_and_up_from_transcribr_and_warnings_from_libraries(tmp_path: Path) -> None:
    stdout = io.StringIO()
    setup_service_logging("web", tmp_path, stream=stdout)
    logging.getLogger("transcribr.x").info("ours")
    logging.getLogger("transcribr.x").debug("too chatty")
    logging.getLogger("httpx").info("library chatter")
    logging.getLogger("httpx").warning("library warning")
    flush()
    messages = [json.loads(line)["message"] for line in stdout.getvalue().splitlines()]
    assert messages == ["ours", "library warning"]


def test_the_log_file_rotates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs, "LOG_FILE_BYTES", 2000)
    log_file = setup_service_logging("worker", tmp_path, stream=io.StringIO())
    for n in range(400):
        logging.getLogger("transcribr.test").info("line %d of a long run", n)
    flush()
    rotated = sorted(log_file.parent.glob("worker.log.*"))
    assert [p.name for p in rotated] == [f"worker.log.{n}" for n in range(1, 6)]
    assert all(p.stat().st_size <= 2000 for p in [log_file, *rotated])
