"""F02, F03, F08: every session/report endpoint requires auth and ownership (or a clinician link)."""
import pytest

from conftest import auth, link, promote_to_clinician, register, seed_session


@pytest.fixture(scope="module")
def world(client):
    alice, alice_t = register(client)          # patient who owns the session
    eve, eve_t = register(client)              # unrelated patient
    bob, _ = register(client)                  # clinician linked to alice
    carol, _ = register(client)                # clinician NOT linked to alice
    promote_to_clinician(bob)
    promote_to_clinician(carol)
    link(bob, alice)
    # tokens are re-issued after promotion so the role claim is current
    from conftest import PASSWORD
    bob_t = client.post("/auth/login", json={"email": bob, "password": PASSWORD}).json()["access_token"]
    carol_t = client.post("/auth/login", json={"email": carol, "password": PASSWORD}).json()["access_token"]
    sid = seed_session(alice)
    return {"sid": sid, "alice": alice_t, "eve": eve_t, "bob": bob_t, "carol": carol_t}


@pytest.mark.parametrize("path", ["/sessions/{sid}", "/report/{sid}"])
def test_unauthenticated_gets_401(client, world, path):
    assert client.get(path.format(sid=world["sid"])).status_code == 401


@pytest.mark.parametrize("path", ["/sessions/{sid}", "/report/{sid}"])
@pytest.mark.parametrize("who", ["eve", "carol"])
def test_other_users_cannot_read(client, world, path, who):
    r = client.get(path.format(sid=world["sid"]), headers=auth(world[who]))
    assert r.status_code == 404        # not 403: don't confirm the ID exists


@pytest.mark.parametrize("path", ["/sessions/{sid}", "/report/{sid}"])
@pytest.mark.parametrize("who", ["alice", "bob"])
def test_owner_and_linked_clinician_can_read(client, world, path, who):
    r = client.get(path.format(sid=world["sid"]), headers=auth(world[who]))
    assert r.status_code == 200, r.text
    if path.startswith("/report"):
        assert r.content[:4] == b"%PDF"


def test_session_list_only_returns_own_sessions(client, world):
    ids = {s["id"] for s in client.get("/sessions", headers=auth(world["eve"])).json()}
    assert world["sid"] not in ids


def test_debug_links_endpoint_removed(client, world):
    assert client.get("/debug/links", headers=auth(world["bob"])).status_code == 404


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/status", headers={"Origin": "http://localhost:3000",
                                             "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.get("/status", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
