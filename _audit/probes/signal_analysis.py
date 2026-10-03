"""Dissect the metrics on the sample clip: aspect-ratio distortion, outlier-driven
min(), visibility of lower-limb landmarks, and what the 'cadence' counter really counts.
Run from _audit/sandbox.  Usage: python signal_analysis.py <video>
"""
import os, sys, json
import numpy as np, pandas as pd, cv2
sys.path.insert(0, os.getcwd())
from src.core.extract_landmarks import extract_landmarks
from src.core.calculate_angles import add_all_angles, angle_3pts

video = sys.argv[1]
cache = "walk01_landmarks_cache.csv"
if os.path.exists(cache):
    df = pd.read_csv(cache)
else:
    df = extract_landmarks(video); df.to_csv(cache, index=False)
df = add_all_angles(df)
cap = cv2.VideoCapture(video); W, H = cap.get(3), cap.get(4)
out = {"video_wh": [W, H], "frames_with_pose": len(df)}

# 1. Aspect-ratio: recompute knee angles in pixel space
def knee_px(row, a, b, c):
    P = lambda i: (row[f"lm{i}_x"] * W, row[f"lm{i}_y"] * H)
    return angle_3pts(P(a), P(b), P(c))
df["knee_L_px"] = df.apply(lambda r: knee_px(r, 23, 25, 27), axis=1)
df["knee_R_px"] = df.apply(lambda r: knee_px(r, 24, 26, 28), axis=1)
out["knee_flexion_180_minus_min"] = {
    "L_normalised(app)": round(180 - df.knee_L.min(), 1),
    "L_pixel_space": round(180 - df.knee_L_px.min(), 1),
    "R_normalised(app)": round(180 - df.knee_R.min(), 1),
    "R_pixel_space": round(180 - df.knee_R_px.min(), 1),
}
out["mean_abs_angle_error_norm_vs_px_deg"] = {
    "knee_L": round(float((df.knee_L - df.knee_L_px).abs().mean()), 2),
    "knee_R": round(float((df.knee_R - df.knee_R_px).abs().mean()), 2),
    "max_knee_L": round(float((df.knee_L - df.knee_L_px).abs().max()), 2),
}
# 2. Robust vs min: percentile flexion, how much does the single worst frame drive it
out["knee_flexion_robust_pixel"] = {
    "L_p2": round(180 - np.percentile(df.knee_L_px, 2), 1),
    "R_p2": round(180 - np.percentile(df.knee_R_px, 2), 1),
}
# 3. Visibility of lower-limb landmarks (side view => far leg occluded)
vis = {name: {"mean": round(float(df[f"lm{i}_vis"].mean()), 3),
              "pct_frames_below_0.5": round(float((df[f"lm{i}_vis"] < 0.5).mean() * 100), 1)}
       for name, i in [("L_hip", 23), ("R_hip", 24), ("L_knee", 25), ("R_knee", 26),
                       ("L_ankle", 27), ("R_ankle", 28)]}
out["visibility"] = vis
# 4. Frame-to-frame jitter of knee angle (deg) - no smoothing in the app
d = df.knee_L.diff().abs()
out["knee_L_frame_to_frame_jump_deg"] = {"median": round(float(d.median()), 2),
                                         "p95": round(float(d.quantile(.95)), 2),
                                         "max": round(float(d.max()), 2)}
# 5. What 'cadence' counts: upward crossings of left knee through 155 deg
k = df.knee_L.values
cross_idx = [i for i in range(1, len(k)) if k[i] > 155 and k[i - 1] <= 155]
dur = df.time_s.max()
out["cadence_counter"] = {
    "duration_s(time_s.max)": dur,
    "left_knee_upcrossings_155": len(cross_idx),
    "crossing_times_s": [round(float(df.time_s.iloc[i]), 2) for i in cross_idx],
    "app_cadence": round(len(cross_idx) / dur * 60, 1),
}
# Crossings that are <0.4 s apart are jitter, not new gait cycles
gaps = np.diff([df.time_s.iloc[i] for i in cross_idx])
out["cadence_counter"]["gaps_s"] = [round(float(g), 2) for g in gaps]
out["cadence_counter"]["crossings_lt_0.4s_apart(jitter)"] = int((gaps < 0.4).sum())
# 6. Detected-frame gaps (frames with no pose silently dropped; time axis has holes)
fr = df.frame.values
out["dropped_frames"] = int((np.diff(fr) - 1).sum())
print(json.dumps(out, indent=1))
