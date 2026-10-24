"""Dissect the metrics on the sample clip: aspect-ratio distortion, outlier-driven min(),
visibility of lower-limb landmarks, frame-to-frame jitter, and what the step counter counts.

v1 (audit): ran the pre-Phase-0 src/ code.
v3 (Plan V3 Phase 2): same questions against gaitcore v2. Usage (repo root, inside the Docker image
because MediaPipe 1.0.1 can't extract on macOS):  python _audit/probes/signal_analysis.py <video>
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.getcwd())
from gaitcore.angles import knee_flexion
from gaitcore.gait import leg_length, measure_walk
from gaitcore.landmarks import extract_clip
from gaitcore.pipeline import analyse
from gaitcore.segments import steady_segments
from gaitcore.signals import build_tracks, raw_xy

clip = extract_clip(sys.argv[1])
W, H = clip.width, clip.height
lm = clip.landmarks
out = {"video_wh": [W, H], "frames_decoded": clip.n_frames,
       "frames_with_pose": int(np.isfinite(lm["lm23_x"]).sum())}

# 1. Aspect ratio: normalised-coordinate angles (pre-V3) vs pixel space (v2 uses pixels)
def interior(P):
    u, v = P[0] - P[1], P[2] - P[1]
    return np.degrees(np.arccos(np.clip((u * v).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(v, axis=1), -1, 1)))
def norm(i):
    return np.c_[lm[f"lm{i}_x"], lm[f"lm{i}_y"]]
px = {s: interior([raw_xy(clip, i) for i in idx]) for s, idx in (("L", (23, 25, 27)), ("R", (24, 26, 28)))}
nm = {s: interior([norm(i) for i in idx]) for s, idx in (("L", (23, 25, 27)), ("R", (24, 26, 28)))}
out["mean_abs_angle_error_norm_vs_px_deg"] = {s: round(float(np.nanmean(np.abs(nm[s] - px[s]))), 2) for s in "LR"}
out["v2_uses"] = "pixel space (frame size applied before any angle)"

# 2. min() vs per-stride peaks
tracks = build_tracks(clip); L = leg_length(tracks)
segs = steady_segments(clip, tracks, L)
walk = measure_walk(clip, segs, tracks=tracks)
out["knee_flexion_pre_v3_180_minus_min_px"] = {s: round(float(180 - np.nanmin(px[s])), 1) for s in "LR"}
out["knee_flexion_v2_per_stride_peaks"] = {s: [round(v, 1) for v in walk.knee_peak_flexion[s]] for s in "LR"}

# 3. Visibility of lower-limb landmarks
out["visibility"] = {n: {"mean": round(float(np.nanmean(lm[f"lm{i}_vis"])), 3),
                         "pct_frames_below_0.5": round(float((lm[f"lm{i}_vis"] < 0.5).mean() * 100), 1)}
                     for n, i in [("L_knee", 25), ("R_knee", 26), ("L_heel", 29), ("R_heel", 30)]}

# 4. Frame-to-frame jitter of the left knee angle: raw pixel angle vs v2 (masked + 6 Hz filtered)
raw_jump = np.abs(np.diff(180 - px["L"])); raw_jump = raw_jump[np.isfinite(raw_jump)]
v2 = knee_flexion(tracks[("L", "hip")], tracks[("L", "knee")], tracks[("L", "ankle")], 1.0)
v2_jump = np.abs(np.diff(v2)); v2_jump = v2_jump[np.isfinite(v2_jump)]
q = lambda a: {"median": round(float(np.median(a)), 2), "p95": round(float(np.percentile(a, 95)), 2), "max": round(float(a.max()), 2), "n": int(len(a))}
out["knee_L_frame_to_frame_jump_deg"] = {"raw_pixel": q(raw_jump), "v2_masked_filtered": q(v2_jump)}

# 5. What the step counter counts: v2 = heel strikes of both feet inside steady passes
out["steady_passes_s"] = [[round(g.start / clip.fps, 2), round(g.end / clip.fps, 2)] for g in segs]
out["heel_strikes_s"] = {s: [round(f / clip.fps, 2) for f in walk.heel_strikes[s]] for s in "LR"}
out["steps"] = len(walk.step_times)
d = analyse(clip).to_dict()
out["v2_result"] = {"status": d["status"], "rejection": d["rejection"], "cadence": d["metrics"].get("cadence")}

# 6. Frames with no detection: kept as NaN rows on a uniform timeline (pre-V3 dropped them silently)
out["frames_without_pose_kept_as_gaps"] = int((~np.isfinite(lm["lm23_x"])).sum())
print(json.dumps(out, indent=1))
