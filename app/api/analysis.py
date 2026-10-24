"""POST /analyze: upload -> quality gate -> measurements (synchronous until Plan V3 Phase 4).

A clip that fails the quality gate is not stored: the response is 422 with
{"detail": {"code": ..., "message": ...}}, the message telling the user what to change.
"""

import logging
import os
import resource
import threading
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.copy import DISCLAIMER
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Session as SessionModel
from app.db.models import User
from app.schemas import AnalyzeResponse, Result
from gaitcore.calibration import Calibration, CalibrationError
from gaitcore.landmarks import VideoReadError, extract_clip
from gaitcore.pipeline import analyse, precheck, probe
from gaitcore.result import AnalysisResult

VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

log = logging.getLogger("gaitscan")
# One pose-model run per process: the handler runs in FastAPI's thread pool (health checks stay
# responsive, F13), but parallel runs would multiply peak memory (~350-490 MB each, F14).
# Plan V3 Phase 4 replaces this with a background task and a status endpoint.
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


def run_pipeline(path: str, calibration: Calibration | None) -> AnalysisResult:
    with _PIPELINE_LOCK:
        try:
            return _run_pipeline(path, calibration)
        finally:
            if settings.analysis_log_memory:
                # High-water mark of the whole process so far, in KiB on Linux.
                log.info(
                    "analysis peak_rss_mb=%d", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                )


def _run_pipeline(path: str, calibration: Calibration | None) -> AnalysisResult:
    info = probe(path)
    result = precheck(info)
    if result is None:
        if calibration is not None:
            calibration.check(info.width, info.height)
        result = analyse(extract_clip(path), calibration)
    return result


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    video: UploadFile = File(...),
    patient_name: str = Form("Anonymous"),
    calib_x1: float | None = Form(None),
    calib_y1: float | None = Form(None),
    calib_x2: float | None = Form(None),
    calib_y2: float | None = Form(None),
    calib_distance_m: float | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> AnalyzeResponse:
    ext = os.path.splitext((video.filename or "").lower())[1]
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Only .mp4, .mov, .avi files accepted")
    calibration = parse_calibration([calib_x1, calib_y1, calib_x2, calib_y2], calib_distance_m)

    job_id = str(uuid.uuid4())
    video_path = f"data/raw/{job_id}{ext}"
    try:
        save_upload(video.file, video_path, settings.max_upload_bytes)
        try:
            result = run_pipeline(video_path, calibration)
        except VideoReadError:
            raise HTTPException(
                422, "We couldn't read this file as a video. Please upload an .mp4, .mov or .avi recording."
            ) from None
        except CalibrationError as e:
            raise rejected("bad_calibration", str(e)) from None
        if not result.accepted:
            assert result.rejection is not None
            raise rejected(result.rejection.code, result.rejection.message)

        data = result.to_dict()
        db.add(
            SessionModel(
                id=job_id,
                patient_name=patient_name,
                user_id=current_user.id,
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
    except HTTPException:
        raise
    except Exception:
        ref = uuid.uuid4().hex[:12]
        log.exception("analysis failed ref=%s job=%s", ref, job_id)
        raise HTTPException(500, f"Analysis failed due to an internal error. Reference: {ref}") from None
    finally:
        # The raw video is never kept, whatever happened.
        if os.path.exists(video_path):
            os.remove(video_path)


def save_upload(src, dest: str, limit: int) -> None:
    """Stream the upload to disk, aborting with 413 once it exceeds `limit` bytes."""
    written = 0
    with open(dest, "wb") as f:
        while chunk := src.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                raise HTTPException(413, f"Video is larger than {limit // (1024 * 1024)} MB.")
            f.write(chunk)
