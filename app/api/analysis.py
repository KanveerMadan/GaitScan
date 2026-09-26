"""POST /analyze: synchronous upload -> analysis -> PDF (moves to a worker in Phase 3)."""

import logging
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Exercise, Finding, Session as SessionModel, User
from app.services.exercises import get_exercise_prescription
from app.services.plots import generate_plots
from app.services.report_pdf import generate_pdf_report
from gaitcore.activity import classify_activity
from gaitcore.angles import add_all_angles
from gaitcore.landmarks import VideoReadError, extract_landmarks
from gaitcore.legacy import DISCLAIMER, calculate_risk_scores

VALID_MODES = {"Clinical", "Runner", "Athlete", "Elderly"}
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

log = logging.getLogger("gaitscan")
router = APIRouter(tags=["analysis"])


@router.post("/analyze")
async def analyze(
    video: UploadFile = File(...),
    patient_name: str = Form("Anonymous"),
    mode: str = Form("Clinical"),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    ext = os.path.splitext((video.filename or "").lower())[1]
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "Only .mp4, .mov, .avi files accepted")

    if mode not in VALID_MODES:
        mode = "Clinical"

    job_id = str(uuid.uuid4())
    video_path = f"data/raw/{job_id}{ext}"
    output_dir = f"outputs/{job_id}"
    succeeded = False

    try:
        save_upload(video.file, video_path, settings.max_upload_bytes)
        os.makedirs(output_dir, exist_ok=True)
        try:
            df = extract_landmarks(video_path)
        except VideoReadError:
            raise HTTPException(
                422, "We couldn't read this file as a video. Please upload an .mp4, .mov or .avi recording."
            )
        if len(df) < 10:
            raise HTTPException(400, "Could not detect a person in the video.")

        df = add_all_angles(df)

        activity_result = classify_activity(df)

        results = calculate_risk_scores(df, activity=activity_result["activity"], mode=mode)
        results["activity"] = activity_result
        results["exercises"] = get_exercise_prescription(
            results["findings"],
            activity_result["activity"],
            results["scores"],
            results["risk_label"],
            mode=mode,
        )

        generate_plots(df, output_dir=output_dir)
        pdf_path = f"{output_dir}/gaitscan_report.pdf"
        generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)

        s = results["scores"]
        session_row = SessionModel(
            id=job_id,
            patient_name=patient_name,
            mode=mode,
            user_id=current_user.id,
            activity=activity_result["activity"],
            confidence=int(activity_result.get("confidence", 0)),
            risk_score=int(s.get("overall_risk_score", 0)),
            risk_label=results["risk_label"],
            risk_color=results["risk_color"],
            risk_meaning=results["risk_meaning"],
            cadence=float(s.get("cadence", 0)),
            knee_si=float(s.get("knee_symmetry_index", 0)),
            hip_si=float(s.get("hip_symmetry_index", 0)),
            knee_flex_L=float(s.get("knee_flexion_range_L", 0)),
            knee_flex_R=float(s.get("knee_flexion_range_R", 0)),
        )
        db.add(session_row)

        for f in results["findings"]:
            db.add(
                Finding(
                    session_id=job_id,
                    metric=f["metric"],
                    value=f["value"],
                    status=f["status"],
                    plain_english=f["plain_english"],
                )
            )

        for ex in results["exercises"]:
            db.add(
                Exercise(
                    session_id=job_id,
                    name=ex["name"],
                    muscle=ex["muscle"],
                    difficulty=ex["difficulty"],
                    instructions=ex["instructions"],
                    why=ex["why"],
                )
            )

        db.commit()
        succeeded = True

        return JSONResponse(
            {
                "job_id": job_id,
                "status": "success",
                "mode": mode,
                "mode_description": results.get("mode_description", ""),
                "activity": results["activity"],
                "risk_label": results["risk_label"],
                "risk_meaning": results["risk_meaning"],
                "risk_color": results["risk_color"],
                "scores": results["scores"],
                "findings": results["findings"],
                "recommendations": results["recommendations"],
                "exercises": results["exercises"],
                "report_url": f"/report/{job_id}",
                "disclaimer": DISCLAIMER,
            }
        )

    except HTTPException:
        raise
    except Exception:
        ref = uuid.uuid4().hex[:12]
        log.exception("analysis failed ref=%s job=%s", ref, job_id)
        raise HTTPException(500, f"Analysis failed due to an internal error. Reference: {ref}")
    finally:
        # The raw video is never kept, whatever happened; partial outputs are dropped on failure.
        if os.path.exists(video_path):
            os.remove(video_path)
        if not succeeded:
            shutil.rmtree(output_dir, ignore_errors=True)


def save_upload(src, dest: str, limit: int) -> None:
    """Stream the upload to disk, aborting with 413 once it exceeds `limit` bytes."""
    written = 0
    with open(dest, "wb") as f:
        while chunk := src.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                raise HTTPException(413, f"Video is larger than {limit // (1024 * 1024)} MB.")
            f.write(chunk)
