"""Per-user settings (Plan V3 Phase 9): re-test interval, display units, language and theme. Nothing
personal beyond what a feature uses (no height: nothing measures with it)."""

import json

import pytest
from conftest import auth, register

DEFAULTS = {
    "retest_weeks": None,
    "units": "metric",
    "language": "en",
    "theme": "system",
    "goal_cadence": None,
}


def test_new_accounts_have_the_defaults(client):
    _, token = register(client)
    assert client.get("/me/settings", headers=auth(token)).json() == DEFAULTS


def test_settings_change_one_field_at_a_time_and_stay_changed(client):
    _, token = register(client)
    r = client.patch("/me/settings", headers=auth(token), json={"retest_weeks": 4})
    assert r.status_code == 200 and r.json() == {**DEFAULTS, "retest_weeks": 4}
    client.patch("/me/settings", headers=auth(token), json={"theme": "dark", "language": "hi"})
    assert client.get("/me/settings", headers=auth(token)).json() == {
        **DEFAULTS,
        "retest_weeks": 4,
        "theme": "dark",
        "language": "hi",
    }
    client.patch("/me/settings", headers=auth(token), json={"retest_weeks": None})
    assert client.get("/me/settings", headers=auth(token)).json()["retest_weeks"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"retest_weeks": 3},
        {"retest_weeks": 0},
        {"units": "furlongs"},
        {"language": "fr"},
        {"theme": "neon"},
        {"height_cm": 180},
        {"goal_cadence": 30},
        {"goal_cadence": 250},
    ],
)
def test_unknown_or_out_of_range_values_are_refused(client, body):
    _, token = register(client)
    assert client.patch("/me/settings", headers=auth(token), json=body).status_code == 422


def test_settings_need_sign_in(client):
    assert client.get("/me/settings").status_code == 401
    assert client.patch("/me/settings", json={"theme": "dark"}).status_code == 401


def test_settings_are_in_the_export(client):
    _, token = register(client)
    client.patch("/me/settings", headers=auth(token), json={"retest_weeks": 2, "units": "imperial"})
    data = json.loads(client.get("/me/export", headers=auth(token)).content)
    assert data["settings"] == {**DEFAULTS, "retest_weeks": 2, "units": "imperial"}


def test_sign_in_returns_the_settings(client):
    email, token = register(client)
    client.patch("/me/settings", headers=auth(token), json={"theme": "dark", "retest_weeks": 4})
    from conftest import PASSWORD

    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.json()["settings"] == {**DEFAULTS, "theme": "dark", "retest_weeks": 4}


def test_a_cadence_goal_is_the_users_own_number_and_can_be_cleared(client):
    _, token = register(client)
    assert (
        client.patch("/me/settings", headers=auth(token), json={"goal_cadence": 112}).json()["goal_cadence"]
        == 112
    )
    assert (
        client.patch("/me/settings", headers=auth(token), json={"goal_cadence": None}).json()["goal_cadence"]
        is None
    )
