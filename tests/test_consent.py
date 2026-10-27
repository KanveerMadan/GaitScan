"""Consent before the first analysis (ADR-007, Plan V3 Phase 5): versioned text, withdrawable,
history kept; analyses are refused without active consent."""

from conftest import auth, fake_video, register

from app.core.copy import CONSENT_VERSION


def video(client, token, path="/analyses"):
    return client.post(path, headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})


def test_a_new_account_has_no_consent_and_sees_the_current_text(client):
    _, t = register(client, consent=False)
    c = client.get("/consent", headers=auth(t)).json()
    assert c["active"] is False and c["version"] == CONSENT_VERSION
    assert "18" in c["text"] and "delete" in c["text"].lower() and "not a medical device" in c["text"].lower()


def test_analyses_are_refused_until_consent_is_given(client, monkeypatch):
    fake_video(monkeypatch)
    _, t = register(client, consent=False)
    for path in ("/analyses", "/analyze"):
        r = video(client, t, path)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "consent_required"
    r = client.post("/consent", headers=auth(t), json={"version": CONSENT_VERSION})
    assert r.status_code == 201 and r.json()["active"] is True and r.json()["accepted_at"]
    assert video(client, t).status_code == 202


def test_consent_to_an_outdated_text_is_refused(client):
    _, t = register(client, consent=False)
    r = client.post("/consent", headers=auth(t), json={"version": "1999-01-01"})
    assert r.status_code == 409 and client.get("/consent", headers=auth(t)).json()["active"] is False


def test_withdrawing_consent_stops_new_analyses_and_keeps_the_record(client, monkeypatch):
    fake_video(monkeypatch)
    _, t = register(client)
    assert client.delete("/consent", headers=auth(t)).status_code == 200
    c = client.get("/consent", headers=auth(t)).json()
    assert c["active"] is False and c["history"][0]["withdrawn_at"] is not None
    assert video(client, t).json()["detail"]["code"] == "consent_required"
