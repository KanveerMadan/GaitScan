from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid, pandas as pd

from src.core.extract_landmarks import extract_landmarks
from src.core.calculate_angles import add_all_angles
from src.core.risk_scoring import calculate_risk_scores
from src.core.report_generator import generate_pdf_report
from src.utils.visualise import generate_plots

app = FastAPI(title="GaitScan API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

@app.get("/")
def root():
    return {"message": "GaitScan API is running", "version": "1.0.0"}

@app.post("/analyze")
async def analyze(video: UploadFile = File(...)):
    # Validate file type
    if not video.filename.endswith((".mp4", ".mov", ".avi")):
        raise HTTPException(400, "Only .mp4, .mov, .avi files accepted")

    # Save uploaded video with unique ID
    job_id = str(uuid.uuid4())[:8]
    video_path = f"data/raw/{job_id}.mp4"
    output_dir = f"outputs/{job_id}"
    os.makedirs(output_dir, exist_ok=True)

    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)

    print(f"[{job_id}] Video saved: {video_path}")

    try:
        # Run full pipeline
        print(f"[{job_id}] Extracting landmarks...")
        df = extract_landmarks(video_path)

        if len(df) < 10:
            raise HTTPException(400, "Could not detect a person in the video. Check lighting and ensure full body is visible.")

        print(f"[{job_id}] Calculating angles...")
        df = add_all_angles(df)
        df.to_csv(f"data/processed/{job_id}_angles.csv", index=False)

        print(f"[{job_id}] Scoring...")
        from src.core.activity_classifier import classify_activity
        activity_result = classify_activity(df)
        results = calculate_risk_scores(df, activity=activity_result["activity"])
        results["activity"] = activity_result

        print(f"[{job_id}] Generating plots...")
        generate_plots(df, output_dir=output_dir)

        print(f"[{job_id}] Generating PDF...")
        pdf_path = f"{output_dir}/gaitscan_report.pdf"
        generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)

        # Clean up video file
        os.remove(video_path)

        return JSONResponse({
            "job_id": job_id,
            "status": "success",
            "activity": results["activity"],
            "risk_label": results["risk_label"],
            "risk_meaning": results["risk_meaning"],
            "risk_color": results["risk_color"],
            "scores": results["scores"],
            "findings": results["findings"],
            "recommendations": results["recommendations"],
            "report_url": f"/report/{job_id}"
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

@app.get("/status")
def status():
    return {"status": "healthy", "message": "GaitScan is running"}