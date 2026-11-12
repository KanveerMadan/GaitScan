"""Non-blocking analysis (Plan V3 Phase 4): POST /analyses queues a job, GET /analyses/{id} reports it.

The TestClient runs FastAPI background tasks before returning the response, so a job has finished
by the time the POST returns."""

import os

import pytest
from conftest import auth, fake_video, register


def submit(client, token, data=None, name="walk.mp4"):
    return client.post(
        "/analyses", headers=auth(token), data=data or {}, files={"video": (name, b"x" * 64, "video/mp4")}
    )


def test_a_job_is_queued_and_its_result_stored(client, monkeypatch):
    fake_video(monkeypatch, steps_per_min=110)
    _, t = register(client)
    r = submit(client, t)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "queued" and job["status_url"] == f"/analyses/{job['job_id']}"
    s = client.get(job["status_url"], headers=auth(t)).json()
    assert s["status"] == "done" and s["rejection"] is None and s["error"] is None
    analysis = s["analysis"]
    assert analysis["result"]["metrics"]["cadence"]["value"] == pytest.approx(110, abs=2)
    stored = client.get(f"/sessions/{analysis['job_id']}", headers=auth(t)).json()
    assert stored["result"] == analysis["result"]


def test_a_rejected_clip_reports_the_reason_and_stores_nothing(client, monkeypatch):
    fake_video(monkeypatch, yaw_deg=40)
    _, t = register(client)
    job = submit(client, t).json()
    s = client.get(job["status_url"], headers=auth(t)).json()
    assert s["status"] == "rejected" and s["analysis"] is None
    assert s["rejection"]["code"] == "not_side_view" and len(s["rejection"]["message"]) > 40
    assert client.get("/sessions", headers=auth(t)).json() == []


def test_jobs_are_private(client, monkeypatch):
    fake_video(monkeypatch)
    _, owner = register(client)
    _, other = register(client)
    job = submit(client, owner).json()
    assert client.get(job["status_url"], headers=auth(other)).status_code == 404
    assert client.get(job["status_url"]).status_code == 401


def test_checks_that_need_no_pose_model_answer_straight_away(client, monkeypatch):
    fake_video(monkeypatch, fps=15)
    _, t = register(client)
    r = submit(client, t)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "low_frame_rate"
    assert submit(client, t, data={"test": "sit_to_stand"}).json()["detail"]["code"] == "unsupported_test"
    assert submit(client, t, name="walk.txt").status_code == 400


def test_an_internal_error_fails_the_job_with_a_reference_and_removes_the_video(client, monkeypatch):
    import app.api.analysis as m

    fake_video(monkeypatch)
    paths = []

    def boom(path):
        paths.append(path)
        raise RuntimeError("pose model crashed")

    monkeypatch.setattr(m, "extract_clip", boom)
    _, t = register(client)
    s = client.get(submit(client, t).json()["status_url"], headers=auth(t)).json()
    assert s["status"] == "failed" and "Reference:" in s["error"] and "crashed" not in s["error"]
    assert paths and not os.path.exists(paths[0])


def test_the_video_is_deleted_after_a_successful_job(client, monkeypatch):
    import app.api.analysis as m

    clip, _ = fake_video(monkeypatch)
    seen = []
    monkeypatch.setattr(m, "extract_clip", lambda path: seen.append(path) or clip)
    _, t = register(client)
    submit(client, t)
    assert seen and not os.path.exists(seen[0])


def test_jobs_left_unfinished_by_a_restart_are_marked_failed():
    from app.api.analysis import recover_unfinished_jobs
    from app.db.database import SessionLocal
    from app.db.models import AnalysisJob

    db = SessionLocal()
    try:
        db.add(AnalysisJob(id="stale-job", user_id=None, status="running", test="walk"))
        db.commit()
        recover_unfinished_jobs()
        db.expire_all()
        job = db.get(AnalysisJob, "stale-job")
        assert job.status == "failed" and "restarted" in job.error_message
    finally:
        db.query(AnalysisJob).filter_by(id="stale-job").delete()
        db.commit()
        db.close()


def test_each_job_logs_when_it_starts_and_how_it_ended(client, monkeypatch, capfd):
    """2026-11-12: an analysis on Render showed "Analysing…" with nothing in the logs to say whether
    it was waiting behind another job, still running, or had ended. Each job now logs both ends."""
    import re

    fake_video(monkeypatch)
    _, t = register(client)
    job = submit(client, t).json()
    err = capfd.readouterr().err
    jid = job["job_id"]
    assert re.search(rf"analysis started job={jid} waited_s=\d+\.\d", err), err
    assert re.search(rf"analysis ended job={jid} status=done seconds=\d+\.\d", err), err


def test_a_rejected_or_failed_job_logs_its_status(client, monkeypatch, capfd):
    import app.api.analysis as m

    fake_video(monkeypatch, yaw_deg=40)
    _, t = register(client)
    rejected = submit(client, t).json()["job_id"]
    monkeypatch.setattr(m, "extract_clip", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = submit(client, t).json()["job_id"]
    err = capfd.readouterr().err
    assert f"analysis ended job={rejected} status=rejected" in err
    assert f"analysis ended job={failed} status=failed" in err
