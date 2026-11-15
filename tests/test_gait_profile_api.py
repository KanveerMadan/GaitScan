"""Gait profile in the API (Plan V3 Phase 11, BE-B): verdicts are worked out when a result is read, from
the person's current sex and birth year (so they never go stale and nothing stored is rewritten), in
general-wellness wording (owner decision D4), in English and Hindi (draft)."""

import json
import re
from datetime import date

import pytest
from conftest import auth, fake_video, register

BANNED_EN = re.compile(
    r"abnormal|\bbad\b|\bpoor\b|\bwrong\b|disease|diagnos|parkinson|stroke|\blimp|arthritis|injur|screen|detect|\brefer\b|referral",
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


def test_trends_leave_out_treadmill_tests(client, monkeypatch):
    """Trends are walks over the ground only, as in the app (a treadmill is other conditions)."""
    _, t = register(client)
    fake_video(monkeypatch, passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    analyse(client, t)
    fake_video(monkeypatch, treadmill=True, passes=1, pass_secs=12.0)
    r = client.post(
        "/analyses",
        headers=auth(t),
        files={"video": ("tm.mp4", b"x" * 64, "video/mp4")},
        data={"test": "treadmill", "belt_speed_kmh": "4.3"},
    )
    assert r.status_code == 202, r.text
    status = client.get(r.json()["status_url"], headers=auth(t)).json()
    assert status["analysis"]["result"]["test"] == "treadmill", status
    series = client.get("/me/trends", headers=auth(t)).json()["sessions"]
    assert len(series) == 1 and series[0]["overall"] is not None


def test_a_finding_gives_its_numbers_to_one_decimal_with_the_degree_sign_attached():
    """44.8 below a typical range from 45.2 read "45 ° (typical 45–71 °)": rounded to whole degrees, the
    value looked inside the range, and the degree sign floated."""
    from app.services.gait_profile import present
    from gaitcore.norms import Reference

    profile = {
        "schema": 3,
        "timing": {"cadence": {"value": 110.0, "n": 20, "unit": "steps/min"}, "step_time_cv": {"value": 3.0, "n": 20, "unit": "%"}},
        "kinematics": {"knee_rom": {"value": 44.8, "n": 8, "unit": "deg"}},
        "quality": {"steps": 20, "usable_frame_fraction": 0.6, "leg_visibility": 0.9},
    }  # fmt: skip
    import gaitcore.verdict as V

    real = V.default_reference
    V.default_reference = lambda m, s, a: (
        Reference(58.05, 5.1, 40, "all adults", "ljmu_same_method", "same_method") if m == "knee_rom" else real(m, s, a)
    )  # fmt: skip
    try:
        v = present({"gait_profile": profile}, None)["gait_profile"]["verdict"]
    finally:
        V.default_reference = real
    text = next(o["text"] for o in v["observations"] if o["metric"] == "knee_rom")
    assert "44.8° (typical 45.3–70.8°)" in text["en"], text["en"]
    assert " °" not in text["en"] and " °" not in text["hi"]
    assert "44.8°" in text["hi"]
