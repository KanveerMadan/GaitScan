from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session as DBSession
import logging
import os
import shutil
import uuid

from src.core.config import settings
from src.core.database import get_db, init_db
from src.core.models import Session as SessionModel, Finding, Exercise
from src.models.user import User
from src.core.auth import get_current_user
from src.core.extract_landmarks import VideoReadError, extract_landmarks
from src.core.calculate_angles import add_all_angles
from src.core import legacy_display as display
from src.core.risk_scoring import DISCLAIMER, calculate_risk_scores
from src.core.report_generator import generate_pdf_report
from src.utils.visualise import generate_plots
from src.core.exercise_prescription import get_exercise_prescription
from src.core.activity_classifier import classify_activity
from src.api.auth_router import router as auth_router
from src.api.clinician_router import router as clinician_router
from src.models.clinician_patient import ClinicianInvite, ClinicianPatient

VALID_MODES = {"Clinical", "Runner", "Athlete", "Elderly"}
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

log = logging.getLogger("gaitscan")

# Interactive docs and the OpenAPI schema are only exposed in dev.
_docs = settings.docs_enabled
app = FastAPI(
    title="GaitScan API",
    version="2.1.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.include_router(auth_router)
app.include_router(clinician_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

os.makedirs("data/raw", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"message": "GaitScan API is running", "version": "2.1.0"}

@app.get("/status")
def status():
    return {"status": "healthy", "message": "GaitScan is running"}

@app.post("/analyze")
async def analyze(
    video: UploadFile = File(...),
    patient_name: str = Form("Anonymous"),
    mode: str = Form("Clinical"),                  
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
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
            raise HTTPException(422, "We couldn't read this file as a video. "
                                     "Please upload an .mp4, .mov or .avi recording.")
        if len(df) < 10:
            raise HTTPException(400, "Could not detect a person in the video.")

        df = add_all_angles(df)

        activity_result = classify_activity(df)

        results = calculate_risk_scores(
            df,
            activity=activity_result["activity"],
            mode=mode
        )
        results["activity"] = activity_result
        results["exercises"] = get_exercise_prescription(
            results["findings"],
            activity_result["activity"],
            results["scores"],
            results["risk_label"],
            mode=mode
        )

        generate_plots(df, output_dir=output_dir)
        pdf_path = f"{output_dir}/gaitscan_report.pdf"
        generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)

        s = results["scores"]
        session_row = SessionModel(
            id           = job_id,
            patient_name = patient_name,
            user_id      = current_user.id,
            activity     = activity_result["activity"],
            confidence   = int(activity_result.get("confidence", 0)),
            risk_score   = int(s.get("overall_risk_score", 0)),
            risk_label   = results["risk_label"],
            risk_color   = results["risk_color"],
            risk_meaning = results["risk_meaning"],
            cadence      = float(s.get("cadence", 0)),
            knee_si      = float(s.get("knee_symmetry_index", 0)),
            hip_si       = float(s.get("hip_symmetry_index", 0)),
            knee_flex_L  = float(s.get("knee_flexion_range_L", 0)),
            knee_flex_R  = float(s.get("knee_flexion_range_R", 0)),
        )
        db.add(session_row)

        for f in results["findings"]:
            db.add(Finding(
                session_id    = job_id,
                metric        = f["metric"],
                value         = f["value"],
                status        = f["status"],
                plain_english = f["plain_english"]
            ))

        for ex in results["exercises"]:
            db.add(Exercise(
                session_id   = job_id,
                name         = ex["name"],
                muscle       = ex["muscle"],
                difficulty   = ex["difficulty"],
                instructions = ex["instructions"],
                why          = ex["why"]
            ))

        db.commit()
        succeeded = True

        return JSONResponse({
            "job_id":            job_id,
            "status":            "success",
            "mode":              mode,
            "mode_description":  results.get("mode_description", ""),
            "activity":          results["activity"],
            "risk_label":        results["risk_label"],
            "risk_meaning":      results["risk_meaning"],
            "risk_color":        results["risk_color"],
            "scores":            results["scores"],
            "findings":          results["findings"],
            "recommendations":   results["recommendations"],
            "exercises":         results["exercises"],
            "report_url":        f"/report/{job_id}",
            "disclaimer":        DISCLAIMER,
        })

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


def get_visible_session(db: DBSession, user: User, session_id: str) -> SessionModel:
    """Return the session if `user` owns it or is a clinician linked to its owner.
    Anything else is a 404, so callers can't probe which IDs exist."""
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is not None and s.user_id is not None:
        if s.user_id == user.id:
            return s
        if user.role == "clinician" and db.query(ClinicianPatient).filter(
            ClinicianPatient.clinician_id == user.id,
            ClinicianPatient.patient_id == s.user_id,
        ).first():
            return s
    raise HTTPException(404, "Session not found")


@app.get("/report/{job_id}")
def get_report(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, job_id)
    pdf_path = f"outputs/{s.id}/gaitscan_report.pdf"
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf",
                            filename="gaitscan_report.pdf")

    results = {
        "scores": {
            "overall_risk_score":  s.risk_score,
            "knee_symmetry_index": s.knee_si,
            "hip_symmetry_index":  s.hip_si,
            "knee_flexion_range_L": s.knee_flex_L,
            "knee_flexion_range_R": s.knee_flex_R,
            "cadence":             s.cadence,
        },
        "findings":        [display.finding(f) for f in s.findings],
        "recommendations": [],
        **display.summary(s.risk_score),
        "activity": {
            "activity":    display.activity(s.activity),
            "confidence":  s.confidence,
            "icon":        "🚶",
            "description": f"Detected activity: {display.activity(s.activity)}"
        },
        "exercises": [display.exercise(ex) for ex in s.exercises],
    }

    output_dir = f"outputs/{s.id}"
    os.makedirs(output_dir, exist_ok=True)
    generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)

    return FileResponse(pdf_path, media_type="application/pdf",
                        filename="gaitscan_report.pdf")


@app.get("/sessions")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    sessions = db.query(SessionModel)\
        .filter(SessionModel.user_id == current_user.id)\
        .order_by(SessionModel.created_at.desc()).all()
    return [session_summary(s) for s in sessions]


def session_summary(s: SessionModel) -> dict:
    return {
        "id":           s.id,
        "patient_name": s.patient_name,
        "activity":     display.activity(s.activity),
        "confidence":   s.confidence,
        "risk_score":   s.risk_score,
        **display.summary(s.risk_score),
        "cadence":      s.cadence,
        "knee_si":      s.knee_si,
        "hip_si":       s.hip_si,
        "knee_flex_L":  s.knee_flex_L,
        "knee_flex_R":  s.knee_flex_R,
        "created_at":   s.created_at.isoformat(),
    }


@app.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, session_id)
    return {
        **session_summary(s),
        "findings":   [display.finding(f) for f in s.findings],
        "exercises":  [display.exercise(ex) for ex in s.exercises],
        "disclaimer": DISCLAIMER,
    }
