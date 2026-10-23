import ipaddress
import socket
from collections.abc import Iterator

import pytest

_real_connect = socket.socket.connect


def _is_loopback(address: object) -> bool:
    host = address[0] if isinstance(address, tuple) and address else address
    if not isinstance(host, str):
        return True  # AF_UNIX paths and similar local endpoints
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that connects off this machine, unless it is marked `realsite`.

    Loopback stays allowed: the event loop behind FastAPI's TestClient uses it on Windows.
    """
    if request.node.get_closest_marker("realsite") is None:

        def guarded_connect(sock: socket.socket, address: object) -> None:
            if not _is_loopback(address):
                raise AssertionError(
                    f"tests must not open network connections (got {address!r}; use the fake Ravon)"
                )
            _real_connect(sock, address)  # type: ignore[arg-type]

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("tests must not open network connections (use the fake Ravon)")

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)
        monkeypatch.setattr(socket, "create_connection", refuse)
    yield
