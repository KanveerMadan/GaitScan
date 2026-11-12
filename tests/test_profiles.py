"""Multiple adult profiles per account (Plan V3 Phase 9): one account can measure other adults, e.g.
a partner or a parent. A profile is a name and a birth year; under-18s are refused. Each analysis
names its profile; history can be read per profile. A clinician linked to the account holder sees only
the holder's own sessions, never another profile's."""

import json
from datetime import date

import pytest
from conftest import PASSWORD, auth, fake_video, link, promote_to_clinician, register

ADULT = date.today().year - 40


def make(client, token, name="Mum", birth_year=ADULT, adult=True):
    return client.post(
        "/profiles", headers=auth(token), json={"name": name, "birth_year": birth_year, "is_adult": adult}
    )


def analyse(client, token, profile_id=None):
    data = {} if profile_id is None else {"profile_id": str(profile_id)}
    r = client.post(
        "/analyses", headers=auth(token), data=data, files={"video": ("walk.mp4", b"x" * 64, "video/mp4")}
    )
    assert r.status_code == 202, r.text
    return client.get(r.json()["status_url"], headers=auth(token)).json()["analysis"]["job_id"]


def test_profiles_are_listed_created_renamed_and_deleted(client):
    _, t = register(client)
    assert client.get("/profiles", headers=auth(t)).json() == []
    p = make(client, t).json()
    assert p["name"] == "Mum" and p["birth_year"] == ADULT
    assert (
        client.patch(f"/profiles/{p['id']}", headers=auth(t), json={"name": "Mother"}).json()["name"]
        == "Mother"
    )
    assert [x["name"] for x in client.get("/profiles", headers=auth(t)).json()] == ["Mother"]
    assert client.delete(f"/profiles/{p['id']}", headers=auth(t)).status_code == 204
    assert client.get("/profiles", headers=auth(t)).json() == []


@pytest.mark.parametrize(
    "birth_year, adult",
    [(date.today().year - 10, True), (date.today().year - 17, True), (ADULT, False), (1890, True)],
)
def test_under_18s_and_unconfirmed_ages_are_refused(client, birth_year, adult):
    _, t = register(client)
    r = make(client, t, birth_year=birth_year, adult=adult)
    assert r.status_code == 422


def test_an_analysis_belongs_to_its_profile_and_history_filters_by_profile(client, monkeypatch):
    fake_video(monkeypatch)
    _, t = register(client)
    p = make(client, t).json()
    mine = analyse(client, t)
    hers = analyse(client, t, p["id"])
    assert {s["id"] for s in client.get("/sessions", headers=auth(t)).json()} == {mine, hers}
    only_hers = client.get(f"/sessions?profile_id={p['id']}", headers=auth(t)).json()
    assert [s["id"] for s in only_hers] == [hers] and only_hers[0]["profile_id"] == p["id"]
    assert only_hers[0]["patient_name"] == "Mum"
    assert [s["id"] for s in client.get("/sessions?profile_id=self", headers=auth(t)).json()] == [mine]


def test_someone_elses_profile_cant_be_used_or_changed(client, monkeypatch):
    fake_video(monkeypatch)
    _, a = register(client)
    _, b = register(client)
    p = make(client, a).json()
    r = client.post(
        "/analyses",
        headers=auth(b),
        data={"profile_id": str(p["id"])},
        files={"video": ("walk.mp4", b"x" * 64, "video/mp4")},
    )
    assert r.status_code == 404
    assert client.patch(f"/profiles/{p['id']}", headers=auth(b), json={"name": "x"}).status_code == 404
    assert client.delete(f"/profiles/{p['id']}", headers=auth(b)).status_code == 404


def test_a_linked_clinician_sees_only_the_account_holders_own_sessions(client, monkeypatch):
    fake_video(monkeypatch)
    patient, t = register(client)
    doc, _ = register(client)
    promote_to_clinician(doc)
    link(doc, patient)
    doc_t = client.post("/auth/login", json={"email": doc, "password": PASSWORD}).json()["access_token"]
    p = make(client, t).json()
    mine = analyse(client, t)
    hers = analyse(client, t, p["id"])
    assert client.get(f"/sessions/{mine}", headers=auth(doc_t)).status_code == 200
    assert client.get(f"/sessions/{hers}", headers=auth(doc_t)).status_code == 404
    pid = client.get("/clinician/patients", headers=auth(doc_t)).json()[0]["patient_id"]
    listed = client.get(f"/clinician/patients/{pid}/sessions", headers=auth(doc_t)).json()["sessions"]
    assert [s["id"] for s in listed] == [mine]
    inbox = client.get("/clinician/inbox", headers=auth(doc_t)).json()["items"]
    assert {i["session_id"] for i in inbox} == {mine}


def test_deleting_a_profile_deletes_its_sessions_and_profiles_are_in_the_export(client, monkeypatch):
    fake_video(monkeypatch)
    _, t = register(client)
    p = make(client, t).json()
    hers = analyse(client, t, p["id"])
    data = json.loads(client.get("/me/export", headers=auth(t)).content)
    assert data["profiles"] == [{"id": p["id"], "name": "Mum", "birth_year": ADULT}]
    assert next(s for s in data["sessions"] if s["id"] == hers)["profile_id"] == p["id"]
    client.delete(f"/profiles/{p['id']}", headers=auth(t))
    assert client.get(f"/sessions/{hers}", headers=auth(t)).status_code == 404


def test_sign_in_returns_the_accounts_profiles(client):
    email, t = register(client)
    make(client, t)
    out = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
    assert out["profiles"] == [{"id": out["profiles"][0]["id"], "name": "Mum", "birth_year": ADULT}]


def test_a_profile_can_have_an_optional_sex_that_can_be_changed_and_cleared(client):
    """Reference bands (owner decision 2026-11-12): optional, for the published norms by age and sex."""
    _, t = register(client)
    plain = make(client, t, name="Dad").json()
    assert plain["sex"] is None
    r = client.post(
        "/profiles",
        headers=auth(t),
        json={"name": "Mum", "birth_year": ADULT, "is_adult": True, "sex": "female"},
    )
    assert r.status_code == 201 and r.json()["sex"] == "female"
    pid = r.json()["id"]
    assert client.patch(f"/profiles/{pid}", headers=auth(t), json={"sex": "male"}).json()["sex"] == "male"
    cleared = client.patch(f"/profiles/{pid}", headers=auth(t), json={"sex": None}).json()
    assert cleared["sex"] is None and cleared["name"] == "Mum"
    renamed = client.patch(f"/profiles/{pid}", headers=auth(t), json={"name": "Amma"}).json()
    assert renamed["name"] == "Amma" and renamed["sex"] is None
    assert client.patch(f"/profiles/{pid}", headers=auth(t), json={"sex": "x"}).status_code == 422
    exported = client.get("/me/export", headers=auth(t)).json()
    assert {p["name"]: p["sex"] for p in exported["profiles"]} == {"Dad": None, "Amma": None}
    assert "sex" in exported["settings"] and "birth_year" in exported["settings"]
