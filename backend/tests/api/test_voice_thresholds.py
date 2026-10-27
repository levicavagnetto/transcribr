from tests.api.conftest import Api


def test_the_admin_changes_thresholds(admin: Api) -> None:
    body = admin.client.get("/api/v1/admin/settings").json()
    assert (body["values"]["voice_threshold_low"], body["values"]["voice_threshold_high"]) == (
        0.5,
        0.65,
    )
    fields = {f["key"]: f for f in body["fields"]}
    assert (fields["voice_threshold_low"]["minimum"], fields["voice_threshold_low"]["maximum"]) == (
        0,
        1,
    )
    saved = admin.put(
        "/api/v1/admin/settings", json={"voice_threshold_low": 0.55, "voice_threshold_high": 0.72}
    )
    assert saved.status_code == 200
    assert saved.json()["values"]["voice_threshold_high"] == 0.72


def test_invalid_thresholds_are_rejected_and_the_previous_values_stay(admin: Api) -> None:
    refused = admin.put(
        "/api/v1/admin/settings",
        json={"voice_threshold_low": 0.8, "voice_threshold_high": 0.6, "poll_interval_minutes": 5},
    )
    assert refused.status_code == 422
    error = refused.json()["error"]
    assert (error["code"], error["key"]) == ("invalid_setting", "voice_threshold_low")
    assert error["message"] == "The weak voice match threshold must be below the strong one."
    values = admin.client.get("/api/v1/admin/settings").json()["values"]
    assert (values["voice_threshold_low"], values["voice_threshold_high"]) == (0.5, 0.65)
    assert values["poll_interval_minutes"] == 2  # nothing in the refused change was saved


def rematches(api: Api) -> int:
    count: int = api.db().execute("SELECT count(*) FROM jobs WHERE type = 'rematch'").fetchone()[0]
    return count


def test_a_threshold_change_queues_a_rematch(admin: Api) -> None:
    admin.put("/api/v1/admin/settings", json={"poll_interval_minutes": 5})
    assert rematches(admin) == 0  # other settings don't
    admin.put("/api/v1/admin/settings", json={"voice_threshold_low": 0.5})
    assert rematches(admin) == 0  # nor does saving the same value
    admin.put("/api/v1/admin/settings", json={"voice_threshold_high": 0.7})
    assert rematches(admin) == 1
    admin.put("/api/v1/admin/settings", json={"voice_threshold_low": 0.45})
    assert rematches(admin) == 1  # the pending one covers it
