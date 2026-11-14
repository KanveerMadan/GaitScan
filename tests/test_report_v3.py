"""The full report (Plan V3 Phase 11, BE-C; design note §8, the owner's 2026-11-13 brief): a multi-page
PDF in English or Hindi, built from a stored v3 result and its verdict. Both legs pooled (no left/right,
no symmetry page: decision A); pelvis oscillation is never shown; general-wellness wording (D4)."""

import io
import json
import re
import tracemalloc
from datetime import date, datetime

import pytest
from conftest import auth, fake_video, register
from pypdf import PdfReader
from synthetic import synthetic_clip

from gaitcore.pipeline import analyse

BANNED_EN = re.compile(
    r"abnormal|\bbad\b|\bpoor\b|\bwrong\b|disease|diagnos|parkinson|stroke|\blimp|arthritis|injur|screen|detect|\brefer\b|referral",
    re.I,
)
BANNED_HI = ("असामान्य", "खराब", "गलत", "बीमारी", "रोग", "निदान", "पार्किंसंस", "लकवा", "स्ट्रोक", "गठिया", "चोट")


def result():
    return analyse(synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0]).to_dict()


def build(lang="en", history=None, **kw):
    from app.services.report_pdf import build_report

    return build_report(
        result(),
        patient_name="Asha Rao",
        created_at=datetime(2026, 11, 14, 9, 30),
        lang=lang,
        person=kw.get("person", ("female", 45.0)),
        report_id="9b9e1c2b-0000-4000-8000-000000000000",
        session_number=kw.get("session_number", 1),
        history=history or [],
        goal_cadence=kw.get("goal_cadence"),
    )


def pages(pdf: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(pdf)).pages]


def fonts(pdf: bytes) -> set[str]:
    out = set()
    for p in PdfReader(io.BytesIO(pdf)).pages:
        for f in (p["/Resources"].get("/Font") or {}).values():
            out.add(str(f.get_object()["/BaseFont"]))
    return out


def test_an_english_report_has_the_briefs_sections_with_a_header_and_page_numbers_on_every_page():
    text = pages(build())
    assert len(text) >= 4
    for i, t in enumerate(text, 1):
        assert "GaitScan" in t and "Asha Rao" in t and "9b9e1c2b" in t, i
        assert f"Page {i} of {len(text)}" in t, i
        assert "not a medical assessment" in t, i
    whole = " ".join(text)
    for heading in ("Summary", "Timing and rhythm", "Joint movement", "Recording quality and method"):
        assert heading in whole, heading
    assert "Progress" not in whole  # only when earlier sessions exist
    assert (
        "Looks typical." in text[0]
        or "Worth keeping an eye on." in text[0]
        or "Outside the typical range." in text[0]
    )
    assert "What to do next" in text[0] and "Gait Profile Score" in text[0]
    assert "Age 45" in text[0] and "Female" in text[0] and "Session 1" in text[0]
    assert "general wellness and information" in whole and "not a medical device" in whole


def test_the_report_shows_both_legs_only_and_never_pelvis_oscillation():
    whole = " ".join(pages(build())).lower()
    assert "both legs" in whole
    assert "symmetry" in whole  # says why there is none
    assert "pelvis" not in whole and "pelvic" not in whole
    assert not re.search(r"\b(left|right)\b", whole)  # no per-side values (decision A)


def test_the_timing_and_joint_pages_carry_levels_typical_ranges_error_ranges_and_confidence():
    whole = " ".join(pages(build()))
    for label in (
        "Cadence",
        "Step-time variability",
        "Knee range of motion",
        "Hip range of motion",
        "Ankle range of motion",
        "Trunk lean",
        "Arm swing",
    ):
        assert label in whole, label
    assert "Typical range" in whole and "Error range" in whole and "Data confidence" in whole
    assert "±4.5 steps/min" in whole and "±4.0°" in whole  # cadence (LJMU), hip (Stenum 2021)
    assert "9° more than a sensor worn on the thigh" in whole
    assert "Information" in whole  # information-only metrics carry no level (D3)


def test_the_method_page_lists_the_model_the_pipeline_and_references():
    last = " ".join(pages(build())[-2:])
    for s in ("Pipeline 3.0.0", "MediaPipe", "Mobbs", "Topham", "Stenum", "Baker", "Zeni", "Fukuchi"):
        assert s in last, s
    assert "Snapshots" in last or "Skeleton" in last


def test_wording_never_uses_banned_words_in_either_language():
    from app.core.report_copy import REPORT

    for lang in ("en", "hi"):
        text = json.dumps(REPORT[lang], ensure_ascii=False)
        if lang == "en":
            assert not BANNED_EN.search(text), BANNED_EN.search(text)
        assert not any(w in text for w in BANNED_HI), lang
    text = " ".join(pages(build()))
    assert not BANNED_EN.search(text), BANNED_EN.search(text)


def test_a_hindi_report_uses_noto_devanagari_and_keeps_latin_text_in_noto_sans():
    pdf = build("hi")
    used = fonts(pdf)
    assert any("NotoSansDevanagari" in f for f in used), used
    assert any(re.search(r"NotoSans-(Regular|Bold)", f) for f in used), used
    assert not any("Helvetica" in f for f in used), used
    text = pages(pdf)
    assert len(text) == len(pages(build("en")))
    assert all("GaitScan" in t and "9b9e1c2b" in t for t in text)


def test_the_progress_page_appears_with_earlier_sessions_and_shows_change_and_the_goal():
    history = [
        {"id": "a", "created_at": "2026-10-01T09:00:00", "overall": "typical", "cadence": 104.0, "step_time_cv": 3.1, "knee_rom": 50.0, "hip_rom": 47.0, "gps": 7.0},
        {"id": "b", "created_at": "2026-10-20T09:00:00", "overall": "keep_an_eye", "cadence": 106.0, "step_time_cv": 2.8, "knee_rom": 52.0, "hip_rom": 49.0, "gps": 6.5},
    ]  # fmt: skip
    text = pages(build(history=history, session_number=3, goal_cadence=112))
    whole = " ".join(text)
    assert "Progress" in whole and "Change since last test" in whole
    assert "Cadence goal: 112 steps/min" in whole
    assert "Session 3" in text[0]


def test_no_age_or_sex_gives_the_all_adults_note():
    whole = " ".join(pages(build(person=None)))
    assert "No age-specific reference for your age; compared with all adults." in whole


def test_the_report_is_deterministic():
    assert build() == build()


def test_building_a_hindi_report_stays_small_in_memory():
    build("hi")  # fonts registered once
    tracemalloc.start()
    build("hi", history=[{"id": "a", "created_at": "2026-10-01T09:00:00", "overall": "typical", "cadence": 104.0, "step_time_cv": 3.1, "knee_rom": 50.0, "hip_rom": 47.0, "gps": 7.0}])  # fmt: skip
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 60 * 1024 * 1024, peak


# ---- API ------------------------------------------------------------------------------------------
@pytest.fixture
def walk(monkeypatch):
    fake_video(monkeypatch, passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")


def analyse_once(client, token):
    r = client.post("/analyses", headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})
    return client.get(r.json()["status_url"], headers=auth(token)).json()["analysis"]["job_id"]


def test_the_report_endpoint_follows_the_language_setting_or_the_query(client, walk):
    _, t = register(client)
    client.patch("/me/settings", headers=auth(t), json={"sex": "male", "birth_year": date.today().year - 30})
    first = analyse_once(client, t)
    sid = analyse_once(client, t)
    en = client.get(f"/report/{sid}", headers=auth(t))
    assert en.status_code == 200 and en.content[:4] == b"%PDF"
    text = pages(en.content)
    assert "Session 2" in text[0] and "Male" in text[0] and "Progress" in " ".join(text)
    hi = client.get(f"/report/{sid}?lang=hi", headers=auth(t))
    assert any("NotoSansDevanagari" in f for f in fonts(hi.content))
    client.patch("/me/settings", headers=auth(t), json={"language": "hi"})
    assert any(
        "NotoSansDevanagari" in f for f in fonts(client.get(f"/report/{first}", headers=auth(t)).content)
    )
    assert client.get(f"/report/{sid}?lang=fr", headers=auth(t)).status_code == 422


def test_every_hindi_word_is_drawable_in_the_font_it_is_set_in():
    """ReportLab shapes a word with one font, so a Devanagari word must not contain characters only
    Noto Sans has (and the reverse)."""
    from app.core.report_copy import REPORT
    from app.core.verdict_copy import COPY
    from app.services.report_full import _register, hindi_words

    cmaps = _register()

    def strings(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from strings(v)
        elif isinstance(o, list):
            for v in o:
                yield from strings(v)
        elif isinstance(o, str):
            yield o

    bad = []
    for text in [*strings(REPORT["hi"]), *strings(COPY["hi"])]:
        for word, deva in hindi_words(text.replace("{", "").replace("}", "")):
            if word.isspace():
                continue
            face = "NotoSansDevanagari" if deva else "NotoSans"
            missing = [ch for ch in word if ord(ch) not in cmaps[face]]
            if missing:
                bad.append((word, missing))
    assert not bad, bad


def test_a_result_stored_before_v3_still_gets_the_v2_report(client):
    from conftest import seed_session

    from app.db.database import SessionLocal
    from app.db.models import Session

    email, t = register(client)
    sid = seed_session(email)
    db = SessionLocal()
    s = db.get(Session, sid)
    old = dict(s.result)
    old.pop("gait_profile", None)
    old["pipeline_version"] = "2.0.0"
    s.result = old
    db.commit()
    db.close()
    text = " ".join(pages(client.get(f"/report/{sid}", headers=auth(t)).content))
    assert "GaitScan walking measurements" in text and "Name: Test Patient" in text
    assert "general wellness and information" in text  # D4 wording in the v2 report too
