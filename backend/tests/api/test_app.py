from tests.api.conftest import Api
from transcribr.store.migrate import MIGRATIONS_DIR, schema_version


def test_health(api: Api) -> None:
    response = api.client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_app_migrates_the_database_on_start(api: Api) -> None:
    assert schema_version(api.db()) == len(list(MIGRATIONS_DIR.glob("*.sql")))


def test_the_ui_is_served_with_a_fallback_for_its_own_routes(api: Api) -> None:
    assert "Transcribr UI" in api.client.get("/").text
    assert "Transcribr UI" in api.client.get("/admin/settings").text
    assert "Transcribr UI" in api.client.get("/calls/26541125").text
    assert api.client.get("/assets/app.js").text == "console.log('app')"


def test_unknown_api_paths_are_json_404s(api: Api) -> None:
    response = api.client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_missing_ui_files_are_404_not_index(api: Api) -> None:
    assert api.client.get("/assets/missing.js").status_code == 404


def test_writes_without_the_request_header_are_refused(api: Api) -> None:
    response = api.client.post("/api/v1/calls/load-earlier")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "missing_request_header"


def test_validation_errors_use_the_error_format(api: Api) -> None:
    response = api.post("/api/v1/auth/login", json={"username": 5})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_no_cross_origin_access_is_granted(api: Api) -> None:
    response = api.client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
