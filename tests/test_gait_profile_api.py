"""Gait profile in the API (Plan V3 Phase 11, BE-B): verdicts are worked out when a result is read, from
the person's current sex and birth year (so they never go stale and nothing stored is rewritten), in
general-wellness wording (owner decision D4), in English and Hindi (draft)."""

import json
import re
from datetime import date

import pytest
from conftest import auth, fake_video, register

BANNED_EN = re.compile(
    r"abnormal|\bbad\b|\bpoor\b|\bwrong\b|disease|diagnos|parkinson|stroke|\blimp|arthritis|injur|screen|detect|refer",
    re.I,
)
BANNED_HI = ("असामान्य", "खराब", "गलत", "बीमारी", "रोग", "निदान", "पार्किंसंस", "लकवा", "स्ट्रोक", "गठिया", "चोट")


def analyse(client, token):
    r = client.post("/analyses", headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 202, r.text
    return client.get(r.json()["status_url"], headers=auth(token)).json()["analysis"]


@pytest.fixture
def walk(monkeypatch):
    fake_video(monkeypatch, passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")


def test_a_result_carries_its_profile_and_a_verdict_in_both_languages(client, walk):
    _, t = register(client)
    res = analyse(client, t)["result"]
    p = res["gait_profile"]
    assert p["schema"] == 3 and res["pipeline_version"] == "3.0.0"
    v = p["verdict"]
    assert v["overall"] in ("typical", "keep_an_eye", "outside")
    assert set(v["summary"]) == {"en", "hi"}
    assert v["notice"]["en"] == "Experimental estimate from a phone video, not a medical assessment."
    assert "general wellness and information" in v["disclaimer"]["en"]
    for m in ("cadence", "step_time_cv", "knee_peak_swing", "knee_rom", "hip_rom", "hip_peak_ext"):
        assert v["metrics"][m]["level"] in ("typical", "slightly_outside", "clearly_outside"), m
        assert v["metrics"][m]["typical"][0] < v["metrics"][m]["typical"][1]


def test_wellness_wording_never_uses_banned_words_in_either_language(client, walk):
    from app.core.verdict_copy import COPY

    for lang in ("en", "hi"):
        text = json.dumps(COPY[lang], ensure_ascii=False)
        if lang == "en":
            assert not BANNED_EN.search(text), BANNED_EN.search(text)
        assert not any(w in text for w in BANNED_HI), lang
    assert COPY["en"]["overall"]["outside"] == (
        "Outside the typical range. If you have concerns about your walking, a physiotherapist can assess it properly."
    )
    assert (
        COPY["en"]["overall"]["keep_an_eye"]
        == "Slightly outside the typical range — worth re-testing in 2–4 weeks."
    )


def test_the_reference_follows_the_persons_current_sex_and_birth_year(client, walk):
    _, t = register(client)
    sid = analyse(client, t)["job_id"]
    plain = client.get(f"/sessions/{sid}", headers=auth(t)).json()["result"]["gait_profile"]["verdict"]
    assert plain["metrics"]["cadence"]["reference"]["fallback"] == "all_adults"
    assert "No age-specific reference for your age; compared with all adults." in plain["notes"]["en"]
    client.patch(
        "/me/settings", headers=auth(t), json={"sex": "female", "birth_year": date.today().year - 45}
    )
    matched = client.get(f"/sessions/{sid}", headers=auth(t)).json()["result"]["gait_profile"]["verdict"]
    assert matched["metrics"]["cadence"]["reference"]["group"] == "women aged 41–50"
    assert matched["metrics"]["cadence"]["reference"]["source"] == "mobbs2025"
    assert (
        matched["metrics"]["knee_rom"]["reference"]["label"]["en"]
        == "compared with healthy adults measured by this app"
    )


def test_a_shared_link_compares_with_all_adults_so_it_reveals_no_age_or_sex(client, walk):
    _, t = register(client)
    client.patch("/me/settings", headers=auth(t), json={"sex": "male", "birth_year": date.today().year - 30})
    sid = analyse(client, t)["job_id"]
    share = client.post(f"/sessions/{sid}/shares", headers=auth(t), json={}).json()
    shared = client.post("/shared", json={"token": share["url"].split("#token=")[1]}).json()
    v = shared["result"]["gait_profile"]["verdict"]
    assert v["metrics"]["cadence"]["reference"]["fallback"] == "all_adults"
    assert "men aged" not in json.dumps(shared)


def test_a_result_stored_before_v3_is_returned_as_it_was(client):
    from conftest import seed_session

    email, t = register(client)
    sid = seed_session(email)
    from app.db.database import SessionLocal
    from app.db.models import Session

    db = SessionLocal()
    s = db.get(Session, sid)
    old = dict(s.result)
    old.pop("gait_profile", None)
    old["pipeline_version"] = "2.0.0"
    s.result = old
    db.commit()
    db.close()
    r = client.get(f"/sessions/{sid}", headers=auth(t))
    assert r.status_code == 200 and r.json()["result"]["gait_profile"] is None


def test_trends_list_each_sessions_key_numbers_and_verdict(client, walk):
    _, t = register(client)
    for _ in range(2):
        analyse(client, t)
    r = client.get("/me/trends", headers=auth(t))
    assert r.status_code == 200
    series = r.json()["sessions"]
    assert len(series) == 2
    for s in series:
        assert {
            "id",
            "created_at",
            "overall",
            "cadence",
            "step_time_cv",
            "knee_rom",
            "hip_rom",
            "gps",
        } <= set(s)
        assert s["overall"] in ("typical", "keep_an_eye", "outside", None)
    assert client.get("/me/trends").status_code == 401
