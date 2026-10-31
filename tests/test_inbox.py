"""Professional inbox (Plan V3 Phase 9): comments on a session between its owner and a linked
clinician, and a clinician's inbox of linked patients' sessions with what is new since they last
looked. Access is the session's: owner or linked clinician; anyone else gets 404."""

import json

import pytest
from conftest import PASSWORD, auth, link, promote_to_clinician, register, seed_session


@pytest.fixture
def world(client):
    alice, alice_t = register(client)  # patient
    eve, eve_t = register(client)  # another patient
    bob, _ = register(client)  # clinician linked to alice
    carol, _ = register(client)  # clinician not linked
    for c in (bob, carol):
        promote_to_clinician(c)
    link(bob, alice)

    def login(email):
        return client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]

    return {
        "sid": seed_session(alice),
        "alice": alice_t,
        "eve": eve_t,
        "bob": login(bob),
        "carol": login(carol),
    }


def post(client, world, who, body):
    return client.post(f"/sessions/{world['sid']}/comments", headers=auth(world[who]), json={"body": body})


def test_the_owner_and_the_linked_clinician_can_comment_and_read_the_thread(client, world):
    assert post(client, world, "bob", "Cadence is up since last month.").status_code == 201
    assert post(client, world, "alice", "New shoes!").status_code == 201
    thread = client.get(f"/sessions/{world['sid']}/comments", headers=auth(world["alice"])).json()
    assert [c["body"] for c in thread] == ["Cadence is up since last month.", "New shoes!"]
    assert [c["author_role"] for c in thread] == ["clinician", "patient"]
    assert all(c["mine"] is (c["author_role"] == "patient") for c in thread)


@pytest.mark.parametrize("who", ["eve", "carol"])
def test_nobody_else_can_read_or_comment(client, world, who):
    assert client.get(f"/sessions/{world['sid']}/comments", headers=auth(world[who])).status_code == 404
    assert post(client, world, who, "hello").status_code == 404


def test_comments_need_sign_in_and_a_sensible_length(client, world):
    assert client.get(f"/sessions/{world['sid']}/comments").status_code == 401
    assert post(client, world, "alice", "").status_code == 422
    assert post(client, world, "alice", "x" * 2001).status_code == 422


def test_the_inbox_lists_linked_patients_sessions_and_what_is_new(client, world):
    inbox = client.get("/clinician/inbox", headers=auth(world["bob"])).json()
    item = next(i for i in inbox["items"] if i["session_id"] == world["sid"])
    assert item["new"] is True and item["comments"] == 0
    assert client.post("/clinician/inbox/seen", headers=auth(world["bob"])).status_code == 204
    item = next(i for i in client.get("/clinician/inbox", headers=auth(world["bob"])).json()["items"])
    assert item["new"] is False
    post(client, world, "alice", "Question about my knee curve")
    item = next(i for i in client.get("/clinician/inbox", headers=auth(world["bob"])).json()["items"])
    assert item["new"] is True and item["comments"] == 1  # a patient's new comment counts as new


def test_the_inbox_is_for_clinicians_and_shows_only_their_patients(client, world):
    assert client.get("/clinician/inbox", headers=auth(world["alice"])).status_code == 403
    items = client.get("/clinician/inbox", headers=auth(world["carol"])).json()["items"]
    assert world["sid"] not in {i["session_id"] for i in items}


def test_comments_go_with_their_session_and_are_in_the_export(client, world):
    post(client, world, "bob", "Looks steady.")
    data = json.loads(client.get("/me/export", headers=auth(world["alice"])).content)
    session = next(s for s in data["sessions"] if s["id"] == world["sid"])
    assert [c["body"] for c in session["comments"]] == ["Looks steady."]
    assert client.delete(f"/sessions/{world['sid']}", headers=auth(world["alice"])).status_code == 204
    from app.db.database import SessionLocal
    from app.db.models import SessionComment

    db = SessionLocal()
    try:
        assert db.query(SessionComment).filter(SessionComment.session_id == world["sid"]).count() == 0
    finally:
        db.close()
