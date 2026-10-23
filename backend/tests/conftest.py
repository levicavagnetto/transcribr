import socket
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that opens a real network connection, unless it is marked `realsite`."""
    if request.node.get_closest_marker("realsite") is None:

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("tests must not open network connections (use the fake Ravon)")

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
    yield
