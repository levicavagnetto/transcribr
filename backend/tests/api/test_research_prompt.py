import pytest

from tests.api.conftest import Api
from transcribr.settings import DEFAULT_RESEARCH_PROMPT, RESEARCH_PROMPT, Settings


def prompt_of(admin: Api) -> str:
    value: str = admin.client.get("/api/v1/admin/settings").json()["values"]["research_prompt"]
    return value


def test_a_new_instance_has_the_shop_default(admin: Api) -> None:
    body = admin.client.get("/api/v1/admin/settings").json()
    assert body["values"]["research_prompt"] == DEFAULT_RESEARCH_PROMPT
    assert "vehicle" in DEFAULT_RESEARCH_PROMPT
    assert "budget or constraints" in DEFAULT_RESEARCH_PROMPT
    fields = {f["key"]: f for f in body["fields"]}
    assert fields["research_prompt"]["label"] == "Research prompt"
    assert (fields["research_prompt"]["min_length"], fields["research_prompt"]["max_length"]) == (
        1,
        4000,
    )


def test_the_admin_edits_the_prompt(admin: Api) -> None:
    edited = "List the parts this customer needs and find three prices for each."
    response = admin.put("/api/v1/admin/settings", json={"research_prompt": edited})
    assert response.status_code == 200
    assert prompt_of(admin) == edited
    assert Settings(admin.db()).get(RESEARCH_PROMPT) == edited


@pytest.mark.parametrize("bad", ["", "   \n  ", "x" * 4001])
def test_an_empty_or_too_long_prompt_is_refused_and_the_old_one_stays(admin: Api, bad: str) -> None:
    response = admin.put("/api/v1/admin/settings", json={"research_prompt": bad})
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["key"]) == ("invalid_setting", "research_prompt")
    assert "1 to 4,000 characters" in error["message"]
    assert prompt_of(admin) == DEFAULT_RESEARCH_PROMPT


def test_exactly_four_thousand_characters_is_fine(admin: Api) -> None:
    response = admin.put("/api/v1/admin/settings", json={"research_prompt": "y" * 4000})
    assert response.status_code == 200
