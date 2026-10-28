"""Read-only share links for one session (Plan V3 Phase 5): random token stored as a hash, sent in the
link's fragment and posted to the API (never in a URL path), 7 days by default, revocable; the shared
view has measurements only, no personal data."""

from datetime import UTC, datetime, timedelta

from conftest import auth, register, seed_session


def make_share(client, t, sid, **body):
    r = client.post(f"/sessions/{sid}/shares", headers=auth(t), json=body)
    assert r.status_code == 201, r.text
    share = r.json()
    assert share["url"].startswith("http://app.test/shared#token=")
    return share, share["url"].split("#token=")[1]


def test_a_share_link_shows_the_measurements_and_nothing_personal(client):
    email, t = register(client, full_name="Asha Rao")
    sid = seed_session(email)
    client.patch(f"/sessions/{sid}", headers=auth(t), json={"notes": "private note"})
    share, token = make_share(client, t, sid)
    expires = datetime.fromisoformat(share["expires_at"])
    assert (
        timedelta(days=6, hours=23)
        < expires.replace(tzinfo=expires.tzinfo or UTC) - datetime.now(UTC)
        <= timedelta(days=7)
    )
    r = client.post("/shared", json={"token": token})  # no login
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["metrics"]["cadence"]["value"] > 0 and "disclaimer" in body
    flat = str(body).lower()
    assert "asha" not in flat and email.lower() not in flat and "private note" not in flat


def test_only_the_owner_creates_lists_and_revokes_links(client):
    email, t = register(client)
    sid = seed_session(email)
    _, other = register(client)
    assert client.post(f"/sessions/{sid}/shares", headers=auth(other), json={}).status_code == 404
    share, token = make_share(client, t, sid, days=1)
    listed = client.get(f"/sessions/{sid}/shares", headers=auth(t)).json()
    assert [s["id"] for s in listed] == [share["id"]] and "url" not in listed[0]
    assert client.delete(f"/shares/{share['id']}", headers=auth(other)).status_code == 404
    assert client.delete(f"/shares/{share['id']}", headers=auth(t)).status_code == 204
    assert client.post("/shared", json={"token": token}).status_code == 404


def test_expired_unknown_and_deleted_session_links_show_nothing(client):
    from app.db.database import SessionLocal
    from app.db.models import ShareLink

    email, t = register(client)
    sid = seed_session(email)
    _, token = make_share(client, t, sid)
    db = SessionLocal()
    for row in db.query(ShareLink).all():
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.close()
    assert client.post("/shared", json={"token": token}).status_code == 404
    assert client.post("/shared", json={"token": "y" * 43}).status_code == 404
    _, token2 = make_share(client, t, sid)
    assert client.delete(f"/sessions/{sid}", headers=auth(t)).status_code == 204
    assert client.post("/shared", json={"token": token2}).status_code == 404


def test_link_lifetime_is_limited(client):
    email, t = register(client)
    sid = seed_session(email)
    for days in (0, 31):
        assert client.post(f"/sessions/{sid}/shares", headers=auth(t), json={"days": days}).status_code == 422
