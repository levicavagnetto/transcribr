import pytest

from tests.api.conftest import Api
from transcribr.cli import main


def test_reset_admin_removes_the_admin_and_prints_a_working_code(
    admin: Api, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(admin.data_dir))
    assert admin.client.get("/api/v1/admin/settings").status_code == 200

    assert main(["reset-admin"]) == 0
    out = capsys.readouterr().out
    code = next(line.split(": ", 1)[1].strip() for line in out.splitlines() if "setup code" in line)

    assert admin.client.get("/api/v1/admin/settings").status_code == 401  # sessions ended
    assert admin.client.get("/api/v1/auth/state").json()["state"] == "setup_required"
    response = admin.post(
        "/api/v1/auth/setup",
        json={"code": code, "username": "new-admin", "password": "a-fresh-passphrase"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "new-admin"


def test_reset_admin_without_a_database_explains(
    tmp_path: object, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRANSCRIBR_DATA_DIR", str(tmp_path))
    assert main(["reset-admin"]) == 1
    assert "no Transcribr database" in capsys.readouterr().err
