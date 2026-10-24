"""Determinism + noise sensitivity + sensitivity to a simulated impairment.

v1 (audit): pre-Phase-0 src/ code, outputs activity/cadence/risk score.
v3 (Plan V3 Phase 2): gaitcore v2; reports what a user would see (status/reason, cadence, per-leg
peak knee flexion). The stiff-knee simulation now also moves the heel and toe with the shank, so the
foot stays attached (the v1 probe moved only the ankle, which v2's heel-based events would ignore).
walk01 is rejected by the v2 quality gate (no complete step in any pass), so the noise and impairment
sections also run on the synthetic overground walker (tests/synthetic.py; synthetic ground truth).
Usage (repo root, inside the Docker image): python _audit/probes/stability.py <video>
"""
import os, sys, json, collections
import numpy as np
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
from dataclasses import replace
from gaitcore.landmarks import extract_clip
from gaitcore.pipeline import analyse
from synthetic import synthetic_clip

def seen(clip):
    d = analyse(clip).to_dict(); m = d["metrics"]
    knee = {k: (v or {}).get("value") for k, v in m.get("peak_knee_flexion", {}).items()}
    return {"status": d["status"], "reason": (d["rejection"] or {}).get("code"),
            "cadence": (m.get("cadence") or {}).get("value"), "peak_knee_flexion": knee}

out = {}
video = sys.argv[1]
# 1. Determinism: two fresh extractions of the same file
a = extract_clip(video); b = extract_clip(video)
xy = [c for c in a.landmarks.columns if c.endswith(("_x", "_y"))]
out["determinism"] = {"same_shape": a.landmarks.shape == b.landmarks.shape,
                      "max_abs_coord_diff": float(np.nanmax(np.abs(a.landmarks[xy].to_numpy() - b.landmarks[xy].to_numpy())))}
out["walk01"] = seen(a)

def noisy(clip, sigma, rng):
    d = clip.landmarks.copy()
    d[xy] = d[xy] + rng.normal(0, sigma, d[xy].shape)
    return replace(clip, landmarks=d)

def stiffen(clip, keep=0.4, side="R"):
    """Shrink one knee's flexion to `keep` of itself: rotate ankle, heel and toe about the knee."""
    hip, knee, ankle, heel, toe = (24, 26, 28, 30, 32) if side == "R" else (23, 25, 27, 29, 31)
    d = clip.landmarks.copy()
    P = lambda i: np.c_[d[f"lm{i}_x"] * clip.width, d[f"lm{i}_y"] * clip.height]
    k, h = P(knee), P(hip)
    ang = lambda v: np.arctan2(v[:, 1], v[:, 0])
    thigh = ang(k - h); shank = ang(P(ankle) - k)
    rot = (np.angle(np.exp(1j * (shank - thigh))) * keep) - np.angle(np.exp(1j * (shank - thigh)))
    for i in (ankle, heel, toe):
        v = P(i) - k
        c, s = np.cos(rot), np.sin(rot)
        n = np.c_[v[:, 0] * c - v[:, 1] * s, v[:, 0] * s + v[:, 1] * c] + k
        d[f"lm{i}_x"], d[f"lm{i}_y"] = n[:, 0] / clip.width, n[:, 1] / clip.height
    return replace(clip, landmarks=d)

rng = np.random.default_rng(42)
for name, base in (("walk01", a), ("synthetic", synthetic_clip(width=1280, height=720)[0])):
    res = {}
    for sigma in [0.001, 0.002, 0.004]:
        outs = [seen(noisy(base, sigma, rng)) for _ in range(25)]
        cads = [o["cadence"] for o in outs if o["cadence"] is not None]
        res[f"sigma={sigma}"] = {"status_counts": dict(collections.Counter(o["reason"] or "accepted" for o in outs)),
                                 "cadence_min_max": [min(cads), max(cads)] if cads else None}
    res["every_other_frame(15fps)"] = seen(replace(base, landmarks=base.landmarks.iloc[::2].reset_index(drop=True), fps=base.fps / 2))
    res["baseline"] = seen(base)
    res["simulated_60pct_loss_right_knee"] = seen(stiffen(base))
    out[name] = res
print(json.dumps(out, indent=1))
