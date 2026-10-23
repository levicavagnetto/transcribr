from pathlib import Path

import pytest

from transcribr.config import ConfigError, load_config


def test_full_environment() -> None:
    config = load_config(
        {
            "RAVON_USERNAME": "admin@example.com",
            "RAVON_PASSWORD": "s3cret-pass",
            "RAVON_BASE_URL": "https://admin.ravon.net/",
            "TRANSCRIBR_PORT": "8080",
            "TRANSCRIBR_DATA_DIR": "/srv/transcribr",
        }
    )
    assert config.ravon_username == "admin@example.com"
    assert config.ravon_password is not None
    assert config.ravon_password.get_secret_value() == "s3cret-pass"
    assert config.ravon_base_url == "https://admin.ravon.net"
    assert config.port == 8080
    assert config.data_dir == Path("/srv/transcribr")
    assert config.has_ravon_credentials
    assert config.database_path == Path("/srv/transcribr/transcribr.db")


def test_defaults_without_credentials() -> None:
    config = load_config({})
    assert config.ravon_base_url == "https://admin.ravon.net"
    assert config.port == 8000
    assert config.data_dir == Path("/data")
    assert not config.has_ravon_credentials


def test_blank_credentials_count_as_missing() -> None:
    assert not load_config({"RAVON_USERNAME": " ", "RAVON_PASSWORD": ""}).has_ravon_credentials


def test_password_never_appears_in_repr_or_str() -> None:
    config = load_config({"RAVON_USERNAME": "u", "RAVON_PASSWORD": "s3cret-pass"})
    assert "s3cret-pass" not in repr(config)
    assert "s3cret-pass" not in str(config)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"TRANSCRIBR_PORT": "eighty"}, "TRANSCRIBR_PORT"),
        ({"TRANSCRIBR_PORT": "70000"}, "TRANSCRIBR_PORT"),
        ({"RAVON_BASE_URL": "ftp://admin.ravon.net"}, "RAVON_BASE_URL"),
    ],
)
def test_bad_values_name_the_variable(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(env)
