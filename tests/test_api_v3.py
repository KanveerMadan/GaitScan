"""The v2 analysis API (Plan V3 Phase 2): measurements with units, rejections with reasons,
optional floor calibration, legacy sessions labelled and never shown as measurements, reports from
the stored result."""

import io

import pytest
from conftest import PASSWORD, auth, fake_video, link, promote_to_clinician, register, seed_session
from pypdf import PdfReader

REMOVED_KEYS = {
    "activity", "confidence", "risk_score", "overall_risk_score", "risk_label", "risk_meaning",
    "risk_color", "knee_symmetry_index", "hip_symmetry_index", "knee_si", "hip_si", "findings",
    "recommendations", "exercises", "mode", "latest_risk", "flag", "trend",
}  # fmt: skip


def keys(obj):
    if isinstance(obj, dict):
        return set(obj) | set().union(*(keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(keys(v) for v in obj))
    return set()


def upload(client, token, data=None):
    return client.post(
        "/analyze",
        headers=auth(token),
        data=data or {},
        files={"video": ("walk.mp4", b"x" * 64, "video/mp4")},
    )


def pdf_text(content):
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_accepted_analysis_returns_and_stores_measurements(client, monkeypatch):
    fake_video(monkeypatch, steps_per_min=110)
    _, t = register(client)
    r = upload(client, t, data={"mode": "Runner"})  # the old mode field is ignored
    assert r.status_code == 200, r.text
    body = r.json()
    res = body["result"]
    assert res["pipeline_version"] == "2.0.0" and res["status"] == "accepted"
    assert res["metrics"]["cadence"]["value"] == pytest.approx(110, abs=2)
    assert res["metrics"]["cadence"]["unit"] == "steps/min"
    assert res["metrics"]["peak_knee_flexion"]["left"]["unit"] == "deg"
    assert res["quality"]["steps_detected"] >= 6
    assert "step_length" not in res["metrics"]  # no calibration -> absent, not estimated
    assert not keys(body) & REMOVED_KEYS
    stored = client.get(f"/sessions/{body['job_id']}", headers=auth(t)).json()
    assert stored["legacy"] is False and stored["result"] == res
    assert "not a medical device" in stored["disclaimer"].lower()


@pytest.mark.parametrize(
    "code,kwargs",
    [
        ("multiple_people", {"people": 2}),
        ("wrong_orientation", {"rotate90": True}),
        ("feet_not_visible", {"feet_visibility": 0.2}),
        ("not_side_view", {"yaw_deg": 40}),
        ("too_little_walking", {"passes": 1, "pass_secs": 3.4}),
        ("low_frame_rate", {"fps": 15}),
        ("too_short", {"passes": 1, "pass_secs": 2.5}),
    ],
)
def test_rejected_clips_get_a_reason_and_are_not_stored(client, monkeypatch, code, kwargs):
    fake_video(monkeypatch, **kwargs)
    _, t = register(client)
    r = upload(client, t)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == code and len(detail["message"]) > 40
    assert client.get("/sessions", headers=auth(t)).json() == []


def test_floor_calibration_adds_step_length_and_speed(client, monkeypatch):
    _, truth = fake_video(monkeypatch)
    _, t = register(client)
    px = 4.0 / 0.9 * 200  # synthetic leg: 200 px = 0.9 m
    cal = {"calib_x1": 100, "calib_y1": truth.floor_y, "calib_x2": 100 + px, "calib_y2": truth.floor_y}
    r = upload(client, t, data={**cal, "calib_distance_m": 4.0})
    assert r.status_code == 200, r.text
    m = r.json()["result"]["metrics"]
    assert m["step_length"]["value"] == pytest.approx(truth.step_length_m, rel=0.02)
    assert m["walking_speed"]["value"] == pytest.approx(truth.speed_m_s, rel=0.02)
    assert r.json()["result"]["quality"]["calibrated"] is True


@pytest.mark.parametrize(
    "data",
    [
        {"calib_x1": 10, "calib_y1": 10, "calib_x2": 500},  # incomplete
        {"calib_x1": 10, "calib_y1": 10, "calib_x2": 30, "calib_y2": 10, "calib_distance_m": 1},  # 20 px
        {"calib_x1": -50, "calib_y1": 10, "calib_x2": 500, "calib_y2": 10, "calib_distance_m": 2},  # outside
    ],
)
def test_bad_calibration_is_422_with_a_reason(client, monkeypatch, data):
    fake_video(monkeypatch)
    _, t = register(client)
    r = upload(client, t, data=data)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_calibration"


def test_report_is_built_from_the_stored_result(client):
    email, t = register(client)
    sid = seed_session(email)
    text = pdf_text(client.get(f"/report/{sid}", headers=auth(t)).content)
    assert "Cadence" in text and "steps/min" in text and "Peak knee flexion" in text
    assert "not measured" in text or "floor calibration" in text.lower()
    assert "Risk" not in text and "Mode" not in text
    again = pdf_text(client.get(f"/report/{sid}", headers=auth(t)).content)
    assert again == text  # deterministic: rebuilt from the database every time (F15)


def test_legacy_sessions_are_labelled_and_never_shown_as_measurements(client):
    email, t = register(client)
    legacy = seed_session(email, legacy=True)
    current = seed_session(email)
    listed = {s["id"]: s for s in client.get("/sessions", headers=auth(t)).json()}
    assert listed[legacy]["legacy"] is True and listed[legacy]["result"] is None
    assert listed[legacy]["pipeline_version"] == "legacy" and listed[legacy]["note"]
    assert listed[current]["legacy"] is False and listed[current]["result"]["metrics"]["cadence"]
    assert "cadence" not in keys(listed[legacy])  # the archived old cadence is not served
    r = client.get(f"/report/{legacy}", headers=auth(t))
    assert r.status_code == 410


def test_clinician_views_carry_no_removed_metrics(client):
    alice, _ = register(client)
    bob, _ = register(client)
    promote_to_clinician(bob)
    link(bob, alice)
    bob_t = client.post("/auth/login", json={"email": bob, "password": PASSWORD}).json()["access_token"]
    seed_session(alice, legacy=True)
    seed_session(alice)
    patients = client.get("/clinician/patients", headers=auth(bob_t)).json()
    assert patients[0]["session_count"] == 2
    pid = patients[0]["patient_id"]
    sessions = client.get(f"/clinician/patients/{pid}/sessions", headers=auth(bob_t)).json()
    assert sorted(s["legacy"] for s in sessions["sessions"]) == [False, True]
    assert not (keys(patients) | keys(sessions)) & REMOVED_KEYS


def test_openapi_schema_has_no_removed_fields(client):
    from app.main import app

    assert not keys(app.openapi()) & REMOVED_KEYS
