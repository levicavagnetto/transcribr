"""Log setup: the services write JSON lines to stdout and a rotating file; commands write text."""

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from transcribr.redaction import RedactingFormatter, redact

LOG_FILE_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUPS = 5


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Each text field is redacted before it is encoded,
    so JSON escaping can't hide a secret from the redaction."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, str] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info))
        if record.stack_info:
            entry["stack"] = redact(self.formatStack(record.stack_info))
        return json.dumps(entry, ensure_ascii=False)


def setup_service_logging(service: str, data_dir: Path, *, stream: TextIO | None = None) -> Path:
    """Log to stdout and to `<data_dir>/logs/<service>.log`; returns the file's path.

    Each service has its own file, because two processes rotating one file would clash.
    """
    log_file = data_dir / "logs" / f"{service}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(stream or sys.stdout),
        RotatingFileHandler(
            log_file, maxBytes=LOG_FILE_BYTES, backupCount=LOG_FILE_BACKUPS, encoding="utf-8"
        ),
    ]
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.WARNING, handlers=handlers, force=True)
    logging.getLogger("transcribr").setLevel(logging.INFO)
    return log_file


def setup_command_logging() -> None:
    """One-off commands log warnings as plain text to stderr, next to their own output."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
