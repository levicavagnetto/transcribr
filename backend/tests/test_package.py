import importlib

import pytest

from transcribr import __version__, cli

PACKAGES = [
    "transcribr.ravon",
    "transcribr.ingest",
    "transcribr.pipeline",
    "transcribr.attribution",
    "transcribr.store",
    "transcribr.api",
    "transcribr.api.routes",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    importlib.import_module(name)


def test_cli_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "usage: transcribr" in capsys.readouterr().out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
