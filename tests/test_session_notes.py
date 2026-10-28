"""Session notes and tags (Plan V3 Phase 4): the owner can label a session; linked clinicians see it."""

import pytest
from conftest import auth, link, promote_to_clinician, register, seed_session


def owner_with_session(client):
    email, token = register(client)
    return email, token, seed_session(email)


def test_the_owner_adds_notes_and_tags(client):
    _, t, sid = owner_with_session(client)
    r = client.patch(
        f"/sessions/{sid}",
        headers=auth(t),
        json={"notes": "  New shoes  ", "tags": ["shoes", " Morning ", "shoes"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "New shoes" and r.json()["tags"] == ["shoes", "morning"]
    listed = client.get("/sessions", headers=auth(t)).json()[0]
    assert listed["notes"] == "New shoes" and listed["tags"] == ["shoes", "morning"]
    # Fields left out are kept; an empty note clears it.
    assert client.patch(f"/sessions/{sid}", headers=auth(t), json={"tags": []}).json()["notes"] == "New shoes"
    assert client.patch(f"/sessions/{sid}", headers=auth(t), json={"notes": ""}).json()["notes"] is None


@pytest.mark.parametrize(
    "body",
    [{"notes": "x" * 1001}, {"tags": ["t"] * 11}, {"tags": ["x" * 31]}, {"tags": [""]}, {"unknown": 1}],
)
def test_notes_and_tags_have_limits(client, body):
    _, t, sid = owner_with_session(client)
    assert client.patch(f"/sessions/{sid}", headers=auth(t), json=body).status_code == 422


def test_only_the_owner_can_edit_but_a_linked_clinician_sees_them(client):
    email, t, sid = owner_with_session(client)
    client.patch(f"/sessions/{sid}", headers=auth(t), json={"notes": "after physio"})
    doc_email, doc = register(client)
    promote_to_clinician(doc_email)
    link(doc_email, email)
    assert client.patch(f"/sessions/{sid}", headers=auth(doc), json={"notes": "edited"}).status_code == 404
    assert client.get(f"/sessions/{sid}", headers=auth(doc)).json()["notes"] == "after physio"
    _, stranger = register(client)
    assert client.patch(f"/sessions/{sid}", headers=auth(stranger), json={"notes": "x"}).status_code == 404
