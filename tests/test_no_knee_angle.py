"""Knee angle is gone (owner decision 2026-11-12: Phase 8 is cancelled, so it can never be validated).
No analysis returns it, and results stored before the decision show it nowhere: not in any API
response, the data export or the PDF. The ghost replay's stride outline (joint positions, not angles)
stays."""

import io
import json

from conftest import auth, register, seed_session
from pypdf import PdfReader
from synthetic import synthetic_clip

OLD_NOTE = (
    "Left and right legs couldn't be told apart reliably in this video, so peak knee flexion isn't "
    "shown for each leg. Cadence and step time don't depend on telling the legs apart."
)


def knee_angle_in(obj) -> bool:
    """The legacy (v2) knee values. The gait profile (schema 3, 2026-11-13: knee angles back as
    experimental estimates) is left out: its knee measures are new, not the removed v2 ones."""

    def without_profile(o):
        if isinstance(o, dict):
            return {k: without_profile(v) for k, v in o.items() if k != "gait_profile"}
        if isinstance(o, list):
            return [without_profile(v) for v in o]
        return o

    text = json.dumps(without_profile(obj)).lower()
    return any(
        k in text for k in ("peak_knee_flexion", "knee_flexion", "knee flexion", "knee angle", "knee bend")
    )


def with_old_knee_values(sid: str) -> None:
    """Make a stored session look like one analysed before 2026-11-12."""
    from app.db.database import SessionLocal
    from app.db.models import Session

    db = SessionLocal()
    try:
        s = db.get(Session, sid)
        r = json.loads(json.dumps(s.result))
        r["metrics"]["peak_knee_flexion"] = {
            "left": {"value": 56.7, "sd": 0.4, "n": 3, "unit": "deg"},
            "right": None,
        }
        r["accuracy"]["peak_knee_flexion"] = {
            "status": "not_yet_validated",
            "note": "No knee-angle reference yet.",
        }
        r["curves"]["knee_flexion"] = {"unit": "deg", "points": 101, "left": [10.0] * 101, "right": None}
        r["notes"] = [OLD_NOTE]
        s.result = r
        db.commit()
    finally:
        db.close()


def test_an_analysis_returns_no_knee_angle():
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    assert result["status"] == "accepted" and result["metrics"]["cadence"]["value"] > 0
    assert not knee_angle_in(result)
    assert result["curves"].get("stride_outline")  # the ghost replay keeps its outline


def test_no_test_type_describes_a_knee_angle():
    from gaitcore.accuracy import TREADMILL_UNVALIDATED, UNVALIDATED

    assert not knee_angle_in(UNVALIDATED) and not knee_angle_in(TREADMILL_UNVALIDATED)


def test_results_stored_before_show_no_knee_angle_anywhere(client):
    email, t = register(client)
    sid = seed_session(email)
    with_old_knee_values(sid)
    detail = client.get(f"/sessions/{sid}", headers=auth(t)).json()
    assert detail["result"]["metrics"]["cadence"]["value"] > 0
    assert not knee_angle_in(detail)
    assert not knee_angle_in(client.get("/sessions", headers=auth(t)).json())
    share = client.post(f"/sessions/{sid}/shares", headers=auth(t), json={}).json()
    shared = client.post("/shared", json={"token": share["url"].split("#token=")[1]}).json()
    assert shared["result"]["metrics"]["cadence"]["value"] > 0 and not knee_angle_in(shared)
    export = client.get("/me/export", headers=auth(t)).json()
    assert export["sessions"][0]["result"]["metrics"]["cadence"] and not knee_angle_in(export)
    pdf = client.get(f"/report/{sid}", headers=auth(t))
    assert pdf.status_code == 200
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages).lower()
    assert "cadence" in text and "knee" not in text
