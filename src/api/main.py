from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session as DBSession
import shutil, os, uuid

from src.core.database import get_db, init_db
from src.core.models import Session as SessionModel, Finding, Exercise
from src.models.user import User
from src.core.auth import get_current_user
from src.core.extract_landmarks import extract_landmarks
from src.core.calculate_angles import add_all_angles
from src.core.risk_scoring import calculate_risk_scores
from src.core.report_generator import generate_pdf_report
from src.utils.visualise import generate_plots
from src.core.exercise_prescription import get_exercise_prescription
from src.core.activity_classifier import classify_activity
from src.api.auth_router import router as auth_router
from src.api.clinician_router import router as clinician_router
from src.models.clinician_patient import ClinicianInvite, ClinicianPatient 

app = FastAPI(title="GaitScan API", version="2.0.0")
app.include_router(auth_router)
app.include_router(clinician_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

@app.on_event("startup")
def startup():
    from src.models.user import User
    from src.core.models import Session, Finding, Exercise
    from src.models.clinician_patient import ClinicianInvite, ClinicianPatient
    Base.metadata.create_all(bind=engine)
    init_db()

@app.get("/")
def root():
    return {"message": "GaitScan API is running", "version": "2.0.0"}

@app.get("/status")
def status():
    return {"status": "healthy", "message": "GaitScan is running"}

@app.post("/analyze")
async def analyze(
    video: UploadFile = File(...),
    patient_name: str = "Anonymous",
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db)
):
    if not video.filename.endswith((".mp4", ".mov", ".avi")):
        raise HTTPException(400, "Only .mp4, .mov, .avi files accepted")

    job_id = str(uuid.uuid4())[:8]
    video_path = f"data/raw/{job_id}.mp4"
    output_dir = f"outputs/{job_id}"
    os.makedirs(output_dir, exist_ok=True)

    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    try:
        df = extract_landmarks(video_path)
        if len(df) < 10:
            raise HTTPException(400, "Could not detect a person in the video.")

        df = add_all_angles(df)
        df.to_csv(f"data/processed/{job_id}_angles.csv", index=False)

        activity_result = classify_activity(df)
        results = calculate_risk_scores(df, activity=activity_result["activity"])
        results["activity"] = activity_result
        results["exercises"] = get_exercise_prescription(
            results["findings"],
            activity_result["activity"],
            results["scores"],
            results["risk_label"]
        )

        generate_plots(df, output_dir=output_dir)
        pdf_path = f"{output_dir}/gaitscan_report.pdf"
        generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)
        os.remove(video_path)

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

        return JSONResponse({
            "job_id":          job_id,
            "status":          "success",
            "activity":        results["activity"],
            "risk_label":      results["risk_label"],
            "risk_meaning":    results["risk_meaning"],
            "risk_color":      results["risk_color"],
            "scores":          results["scores"],
            "findings":        results["findings"],
            "recommendations": results["recommendations"],
            "exercises":       results["exercises"],
            "report_url":      f"/report/{job_id}"
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.get("/report/{job_id}")
def get_report(job_id: str):
    pdf_path = f"outputs/{job_id}/gaitscan_report.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(404, "Report not found")
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

    return [{
        "id":           s.id,
        "patient_name": s.patient_name,
        "activity":     s.activity,
        "confidence":   s.confidence,
        "risk_score":   s.risk_score,
        "risk_label":   s.risk_label,
        "risk_color":   s.risk_color,
        "cadence":      s.cadence,
        "knee_si":      s.knee_si,
        "hip_si":       s.hip_si,
        "knee_flex_L":  s.knee_flex_L,
        "knee_flex_R":  s.knee_flex_R,
        "created_at":   s.created_at.isoformat(),
    } for s in sessions]

@app.get("/sessions/{session_id}")
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    return {
        "id":           s.id,
        "patient_name": s.patient_name,
        "activity":     s.activity,
        "confidence":   s.confidence,
        "risk_score":   s.risk_score,
        "risk_label":   s.risk_label,
        "risk_color":   s.risk_color,
        "risk_meaning": s.risk_meaning,
        "cadence":      s.cadence,
        "knee_si":      s.knee_si,
        "hip_si":       s.hip_si,
        "knee_flex_L":  s.knee_flex_L,
        "knee_flex_R":  s.knee_flex_R,
        "created_at":   s.created_at.isoformat(),
        "findings": [{
            "metric":        f.metric,
            "value":         f.value,
            "status":        f.status,
            "plain_english": f.plain_english
        } for f in s.findings],
        "exercises": [{
            "name":         ex.name,
            "muscle":       ex.muscle,
            "difficulty":   ex.difficulty,
            "instructions": ex.instructions,
            "why":          ex.why
        } for ex in s.exercises]
    }