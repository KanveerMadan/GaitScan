"""Profile each pipeline stage on a video: wall time + peak RSS.
Run from _audit/sandbox so the app's cwd-relative writes stay out of the repo.
Usage: python profile_pipeline.py <video> [runs]
"""
import os, sys, time, threading, json
import psutil

sys.path.insert(0, os.getcwd())
os.environ.pop("GROQ_API_KEY", None)  # no network: exercise the fallback path

proc = psutil.Process()
peak = {"rss": 0}
stop = False

def sampler():
    while not stop:
        peak["rss"] = max(peak["rss"], proc.memory_info().rss)
        time.sleep(0.02)

threading.Thread(target=sampler, daemon=True).start()
base_rss = proc.memory_info().rss

t = time.perf_counter()
from src.core.extract_landmarks import extract_landmarks
from src.core.calculate_angles import add_all_angles
from src.core.activity_classifier import classify_activity
from src.core.risk_scoring import calculate_risk_scores
from src.core.exercise_prescription import get_exercise_prescription
from src.utils.visualise import generate_plots
from src.core.report_generator import generate_pdf_report
import_s = time.perf_counter() - t

video = sys.argv[1]
timings = {"imports": import_s}

def stage(name, fn):
    t = time.perf_counter()
    out = fn()
    timings[name] = time.perf_counter() - t
    return out

df = stage("decode+mediapipe", lambda: extract_landmarks(video))
df = stage("angles", lambda: add_all_angles(df))
act = stage("classify", lambda: classify_activity(df))
res = stage("risk_scoring", lambda: calculate_risk_scores(df, activity=act["activity"], mode="Clinical"))
res["activity"] = act
res["exercises"] = stage("exercises(no GROQ key)", lambda: get_exercise_prescription(
    res["findings"], act["activity"], res["scores"], res["risk_label"], mode="Clinical"))
os.makedirs("outputs/profile", exist_ok=True)
stage("plots", lambda: generate_plots(df, output_dir="outputs/profile"))
stage("pdf", lambda: generate_pdf_report(res, output_path="outputs/profile/r.pdf", plots_dir="outputs/profile"))
stop = True

print(json.dumps({
    "frames_with_pose": len(df),
    "timings_s": {k: round(v, 3) for k, v in timings.items()},
    "total_s": round(sum(timings.values()), 2),
    "baseline_rss_mb": round(base_rss / 1e6),
    "peak_rss_mb": round(peak["rss"] / 1e6),
    "activity": act,
    "scores": res["scores"],
    "risk_label": res["risk_label"],
    "findings": [(f["metric"], f["value"], f["status"]) for f in res["findings"]],
}, indent=1, default=str))
