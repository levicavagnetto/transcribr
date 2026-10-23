import io
import logging
from collections.abc import Iterator

import pytest

from transcribr.redaction import RedactingFormatter, redact, register_secret

PASSWORD = "Tr1cky&Pass=word"


@pytest.fixture
def capture() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("redaction-test")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield logger, stream
    logger.removeHandler(handler)


def log_records_carrying_secrets(logger: logging.Logger) -> None:
    """Log credentials and cookies in every shape they could reach a log line in."""
    register_secret(PASSWORD)
    logger.info("login form: username=admin@example.com&password=%s", PASSWORD)
    logger.info("request headers: {'Cookie': 'JSESSIONID=ABC123DEF; session=xyz789'}")
    logger.info("response: Set-Cookie: JSESSIONID=QQQ999; Path=/; HttpOnly")
    logger.warning("the password was %r", PASSWORD)
    try:
        raise RuntimeError(f"failed with password {PASSWORD}")
    except RuntimeError:
        logger.exception("login crashed")


def assert_no_secrets(out: str) -> None:
    for secret in (PASSWORD, "ABC123DEF", "xyz789", "QQQ999"):
        assert secret not in out
    assert "[redacted]" in out
    assert "username=admin@example.com" in out  # usernames are fine to log


def test_registered_secrets_and_cookies_never_reach_the_log(
    capture: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = capture
    log_records_carrying_secrets(logger)
    assert_no_secrets(stream.getvalue())


def test_redact_handles_form_and_query_style_passwords() -> None:
    text = redact("POST /auth/login password=hunter2&username=a and ?pass=abc")
    assert "hunter2" not in text
    assert "username=a" in text


def test_short_secrets_are_ignored_to_avoid_mangling_logs() -> None:
    register_secret("ab")
    assert redact("tab table") == "tab table"
