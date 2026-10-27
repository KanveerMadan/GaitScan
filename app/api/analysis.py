"""Upload -> quality gate -> measurements.

POST /analyses queues the analysis as a background task and returns 202 with a status URL to poll
(GET /analyses/{id}); POST /analyze is the older synchronous form. A clip that fails the quality gate
is not stored: its reason is a {"code", "message"} pair, the message telling the user what to change
(422 straight away for checks that need no pose model; the job's `rejection` otherwise).
"""

import logging
import os
import resource
import threading
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from app.api.consent import require_consent
from app.core.config import settings
from app.core.copy import DISCLAIMER
from app.core.security import get_current_user
from app.db.database import SessionLocal, get_db
from app.db.models import AnalysisJob, User
from app.db.models import Session as SessionModel
from app.schemas import AnalyzeResponse, JobQueued, JobStatus, Rejection, Result
from gaitcore.calibration import Calibration, CalibrationError
from gaitcore.landmarks import VideoReadError, extract_clip
from gaitcore.pipeline import TESTS, analyse, precheck, probe
from gaitcore.result import WALK, AnalysisResult

VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

log = logging.getLogger("gaitscan")
# One pose-model run per process: the handler runs in FastAPI's thread pool (health checks stay
# responsive, F13), but parallel runs would multiply peak memory (~350-490 MB each, F14).
# Background jobs (POST /analyses) take the same lock, so they run one after another.
_PIPELINE_LOCK = threading.Lock()
router = APIRouter(tags=["analysis"])


def rejected(code: str, message: str) -> HTTPException:
    return HTTPException(422, {"code": code, "message": message})


def parse_calibration(values: list[float | None], distance_m: float | None) -> Calibration | None:
    given = [*values, distance_m]
    if all(v is None for v in given):
        return None
    if any(v is None for v in given):
        raise rejected(
            "bad_calibration",
            "Floor calibration needs both points (calib_x1, calib_y1, calib_x2, calib_y2, in video pixels) "
            "and the distance between them in metres (calib_distance_m).",
        )
    x1, y1, x2, y2 = (float(v) for v in values if v is not None)
    return Calibration(x1, y1, x2, y2, float(distance_m or 0.0))


def run_pipeline(path: str, calibration: Calibration | None, test: str = WALK) -> AnalysisResult:
    with _PIPELINE_LOCK:
        try:
            return _run_pipeline(path, calibration, test)
        finally:
            if settings.analysis_log_memory:
                # High-water mark of the whole process so far, in KiB on Linux.
                log.info(
                    "analysis peak_rss_mb=%d", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                )


def _run_pipeline(path: str, calibration: Calibration | None, test: str) -> AnalysisResult:
    info = probe(path)
    result = precheck(info, test)
    if result is None:
        if calibration is not None:
            calibration.check(info.width, info.height)
        result = analyse(extract_clip(path), calibration, test)
    return result


def _form_checks(
    video: UploadFile, test: str, calibration_values: list[float | None], distance_m: float | None
) -> tuple[str, Calibration | None]:
    """Checks on the request itself, before anything is saved. Returns the file extension."""
    ext = os.path.splitext((video.filename or "").lower())[1]
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Only .mp4, .mov, .avi files accepted")
    if test not in TESTS:
        raise rejected(
            "unsupported_test", f"That test isn't available. Tests you can run: {', '.join(TESTS)}."
        )
    return ext, parse_calibration(calibration_values, distance_m)


UNREADABLE = "We couldn't read this file as a video. Please upload an .mp4, .mov or .avi recording."


def _store(
    db: DBSession, job_id: str, user_id: int, patient_name: str, result: AnalysisResult
) -> AnalyzeResponse:
    data = result.to_dict()
    db.add(
        SessionModel(
            id=job_id,
            patient_name=patient_name,
            user_id=user_id,
            pipeline_version=result.pipeline_version,
            result=data,
        )
    )
    db.commit()
    return AnalyzeResponse(
        job_id=job_id,
        result=Result.model_validate(data),
        report_url=f"/report/{job_id}",
        disclaimer=DISCLAIMER,
    )


def _remove(path: str) -> None:
    # The raw video is never kept, whatever happened.
    if os.path.exists(path):
        os.remove(path)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    video: UploadFile = File(...),
    patient_name: str = Form("Anonymous"),
    test: str = Form(WALK),
    calib_x1: float | None = Form(None),
    calib_y1: float | None = Form(None),
    calib_x2: float | None = Form(None),
    calib_y2: float | None = Form(None),
    calib_distance_m: float | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> AnalyzeResponse:
    """Synchronous analysis (kept until every client uses POST /analyses)."""
    require_consent(db, current_user)
    ext, calibration = _form_checks(video, test, [calib_x1, calib_y1, calib_x2, calib_y2], calib_distance_m)
    job_id = str(uuid.uuid4())
    video_path = f"data/raw/{job_id}{ext}"
    try:
        save_upload(video.file, video_path, settings.max_upload_bytes)
        try:
            result = run_pipeline(video_path, calibration, test)
        except VideoReadError:
            raise HTTPException(422, UNREADABLE) from None
        except CalibrationError as e:
            raise rejected("bad_calibration", str(e)) from None
        if not result.accepted:
            assert result.rejection is not None
            raise rejected(result.rejection.code, result.rejection.message)
        return _store(db, job_id, current_user.id, patient_name, result)
    except HTTPException:
        raise
    except Exception:
        ref = uuid.uuid4().hex[:12]
        log.exception("analysis failed ref=%s job=%s", ref, job_id)
        raise HTTPException(500, f"Analysis failed due to an internal error. Reference: {ref}") from None
    finally:
        _remove(video_path)


@router.post("/analyses", status_code=202, response_model=JobQueued)
def submit_analysis(
    background: BackgroundTasks,
    video: UploadFile = File(...),
    patient_name: str = Form("Anonymous"),
    test: str = Form(WALK),
    calib_x1: float | None = Form(None),
    calib_y1: float | None = Form(None),
    calib_x2: float | None = Form(None),
    calib_y2: float | None = Form(None),
    calib_distance_m: float | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> JobQueued:
    """Queue an analysis and return at once; poll the status_url (Plan V3 Phase 4). Checks that need
    no pose model (file type, test, calibration, length, frame rate) answer here, straight away."""
    require_consent(db, current_user)
    ext, calibration = _form_checks(video, test, [calib_x1, calib_y1, calib_x2, calib_y2], calib_distance_m)
    job_id = str(uuid.uuid4())
    video_path = f"data/raw/{job_id}{ext}"
    queued = False
    try:
        save_upload(video.file, video_path, settings.max_upload_bytes)
        try:
            info = probe(video_path)
        except VideoReadError:
            raise HTTPException(422, UNREADABLE) from None
        early = precheck(info, test)
        if early is not None:
            assert early.rejection is not None
            raise rejected(early.rejection.code, early.rejection.message)
        if calibration is not None:
            try:
                calibration.check(info.width, info.height)
            except CalibrationError as e:
                raise rejected("bad_calibration", str(e)) from None
        db.add(
            AnalysisJob(
                id=job_id, user_id=current_user.id, status="queued", test=test, patient_name=patient_name
            )
        )
        db.commit()
        background.add_task(process_job, job_id, video_path, calibration, test)
        queued = True
        return JobQueued(job_id=job_id, status="queued", status_url=f"/analyses/{job_id}")
    finally:
        if not queued:
            _remove(video_path)


def process_job(job_id: str, video_path: str, calibration: Calibration | None, test: str) -> None:
    """Run one queued job (FastAPI background task; runs after the 202 is sent)."""
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = "running"
        db.commit()
        try:
            result = run_pipeline(video_path, calibration, test)
            if result.accepted:
                assert job.user_id is not None
                _store(db, job_id, job.user_id, job.patient_name or "Anonymous", result)
                job.status, job.session_id = "done", job_id
            else:
                assert result.rejection is not None
                job.status, job.error_code, job.error_message = (
                    "rejected",
                    result.rejection.code,
                    result.rejection.message,
                )
        except VideoReadError:
            job.status, job.error_code, job.error_message = "rejected", "unreadable_video", UNREADABLE
        except Exception:
            db.rollback()
            ref = uuid.uuid4().hex[:12]
            log.exception("analysis failed ref=%s job=%s", ref, job_id)
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            job.status = "failed"
            job.error_message = f"Analysis failed due to an internal error. Reference: {ref}"
        job.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
        _remove(video_path)


@router.get("/analyses/{job_id}", response_model=JobStatus)
def analysis_status(
    job_id: str, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> JobStatus:
    job = db.get(AnalysisJob, job_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(404, "Analysis not found")
    analysis = None
    if job.status == "done" and job.session_id:
        session = db.get(SessionModel, job.session_id)
        if session is not None and session.result is not None:
            analysis = AnalyzeResponse(
                job_id=session.id,
                result=Result.model_validate(session.result),
                report_url=f"/report/{session.id}",
                disclaimer=DISCLAIMER,
            )
    rejection = (
        Rejection(code=job.error_code or "rejected", message=job.error_message or "")
        if job.status == "rejected"
        else None
    )
    return JobStatus(
        job_id=job.id,
        status=job.status,
        rejection=rejection,
        error=job.error_message if job.status == "failed" else None,
        analysis=analysis,
    )


def recover_unfinished_jobs() -> None:
    """At startup: jobs a previous process left queued or running will never finish (their video is
    gone with the process's temporary state), so they are failed with a reason the user can act on."""
    db = SessionLocal()
    try:
        for job in db.query(AnalysisJob).filter(AnalysisJob.status.in_(("queued", "running"))):
            job.status = "failed"
            job.error_message = (
                "The server restarted before this analysis finished. Please upload the video again."
            )
            job.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def save_upload(src, dest: str, limit: int) -> None:
    """Stream the upload to disk, aborting with 413 once it exceeds `limit` bytes."""
    written = 0
    with open(dest, "wb") as f:
        while chunk := src.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                raise HTTPException(413, f"Video is larger than {limit // (1024 * 1024)} MB.")
            f.write(chunk)
