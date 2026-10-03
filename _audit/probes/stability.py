"""Determinism + noise sensitivity + sensitivity to a simulated impairment.
Run from _audit/sandbox after signal_analysis.py (uses its landmark cache).
"""
import os, sys, json, collections
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd())
from src.core.extract_landmarks import extract_landmarks
from src.core.calculate_angles import add_all_angles
from src.core.activity_classifier import classify_activity
from src.core.risk_scoring import calculate_risk_scores

out = {}
video = sys.argv[1]

# 1. Determinism: two fresh extractions of the same file
a = extract_landmarks(video); b = extract_landmarks(video)
xy = [c for c in a.columns if c.endswith(("_x", "_y"))]
out["determinism"] = {"same_shape": a.shape == b.shape,
                      "max_abs_coord_diff": float((a[xy] - b[xy]).abs().to_numpy().max())}

base = pd.read_csv("walk01_landmarks_cache.csv")

def run(df):
    df = add_all_angles(df)
    act = classify_activity(df)
    r = calculate_risk_scores(df, activity=act["activity"], mode="Clinical")
    return act["activity"], r["scores"]["cadence"], r["scores"]["overall_risk_score"], r["scores"]

# 2. Landmark noise (normalised units; 0.002 ~= 1 px wide x 1.7 px tall on this clip)
rng = np.random.default_rng(42)
xycols = [c for c in base.columns if c.endswith(("_x", "_y"))]
out["noise"] = {}
for sigma in [0.001, 0.002, 0.004]:
    acts, cads, risks = collections.Counter(), [], []
    for _ in range(25):
        d = base.copy()
        d[xycols] = d[xycols] + rng.normal(0, sigma, d[xycols].shape)
        act, cad, risk, _ = run(d)
        acts[act] += 1; cads.append(cad); risks.append(risk)
    out["noise"][f"sigma={sigma}"] = {"activity_counts": dict(acts),
                                      "cadence_min_max": [min(cads), max(cads)],
                                      "risk_scores_seen": sorted(set(risks))}

# 3. Frame-rate: same clip at 15 fps (drop every other frame)
half = base.iloc[::2].reset_index(drop=True)
out["every_other_frame"] = run(half)[:3]

# 4. Simulated right-knee impairment: shrink right knee flexion by 60%
#    (rotate the right ankle about the right knee toward full extension)
def stiffen(df, keep=0.4):
    d = df.copy()
    kx, ky, hx, hy = d.lm26_x, d.lm26_y, d.lm24_x, d.lm24_y
    ax, ay = d.lm28_x - kx, d.lm28_y - ky
    # thigh direction (hip->knee) is where a fully extended shank would point
    tx, ty = kx - hx, ky - hy
    ang_shank = np.arctan2(ay, ax); ang_thigh = np.arctan2(ty, tx)
    diff = np.angle(np.exp(1j * (ang_shank - ang_thigh)))
    new = ang_thigh + diff * keep
    L = np.hypot(ax, ay)
    d["lm28_x"] = kx + L * np.cos(new); d["lm28_y"] = ky + L * np.sin(new)
    return d
act, cad, risk, sc = run(stiffen(base))
out["simulated_stiff_right_knee"] = {"activity": act, "risk": risk,
                                     "knee_flex_L": sc["knee_flexion_range_L"],
                                     "knee_flex_R": sc["knee_flexion_range_R"],
                                     "knee_SI": sc["knee_symmetry_index"]}
print(json.dumps(out))
