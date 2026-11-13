"""Label-free knee and hip measures on LJMU (Plan V3 Phase 11, BE-A2, decision B): `make kinematics`.

Data: LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0), the side-view
clips in ljmu_reference.csv, plus the right-thigh goniometer files for tasks 1-2 when present.

There is no joint-angle reference in LJMU, so what can be checked is:
1. availability: accepted clips with >= 3 label-free strides, against today's labelled per-leg values
   (shown only when result.legs_told_apart);
2. heel-strike timing: the label-free strikes (kinematics.measure_kinematics: where the front heel
   stops) against the reference strikes (AI-annotated / RTMPose, foot-agnostic), within 5 frames;
3. plausibility: stance, double support and knee/hip values against published healthy ranges (Stenum
   et al. 2021 motion capture: stance 0.74 s of a 1.21 s stride, double support 0.14 s per step);
4. thigh range: ours (label-free, both legs) against the sensor's (evaluation.leg_labels), on average
   only (the sensor isn't aligned with the clips: docs/validation/leg-labels.md).

Outputs (--out): kinematics_clips.csv and kinematics.json; written up in docs/validation/kinematics.md.
"""

import argparse
import json
import math
import os
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from evaluation.evaluate import load_clip, load_reference
from evaluation.leg_labels import read_sensor, sensor_strides
from gaitcore.gait import leg_length, measure_walk
from gaitcore.pipeline import analyse, walking
from gaitcore.result import legs_told_apart
from gaitcore.signals import build_tracks

HERE = os.path.dirname(os.path.abspath(__file__))
MATCH_FRAMES = 5  # a strike within this many frames of a reference strike is the same strike
METRICS = (
    "stance_pct",
    "double_support_pct",
    "knee_ic",
    "knee_peak_swing",
    "knee_rom",
    "hip_peak_ext",
    "hip_peak_flex",
    "hip_rom",
    "thigh_rom",
    "ankle_rom",
    "trunk_lean_deg",
    "pelvis_oscillation",
    "arm_swing_deg",
)


def evaluate_clip(ref: Any, clip: Any, sensor_dir: str | None) -> dict[str, Any]:
    r = analyse(clip)
    row: dict[str, Any] = {
        "clip": ref.clip,
        "participant": ref.participant,
        "role": ref.role,
        "accepted": r.accepted,
    }
    if not r.accepted or r.kinematics is None:
        return row
    tracks = build_tracks(clip)
    w = measure_walk(clip, walking(clip, tracks, leg_length(tracks)).segments, tracks=tracks)
    k = r.kinematics
    s = k.summary()
    row.update(strides=len(k.strides), legs_told_apart=legs_told_apart(w))
    for m in METRICS:
        v = s[m]
        row[m] = None if v is None else round(v["value"], 3)
    # Strike timing: every stride start is a strike; the reference strikes inside the steady walking.
    first, last = (
        min(x.start for x in k.strides) if k.strides else 0,
        max(x.end for x in k.strides) if k.strides else 0,
    )
    refs = [f for f in ref.strikes if first - MATCH_FRAMES <= f <= last + MATCH_FRAMES]
    errs = []
    for x in k.strides:
        near = [f - x.start for f in refs if abs(f - x.start) <= MATCH_FRAMES]
        if near:
            errs.append(min(near, key=abs))
    row.update(
        strikes=len(k.strides),
        strikes_matched=len(errs),
        strike_error_frames_median=float(np.median(errs)) if errs else None,
        strike_abs_error_frames_mean=float(np.mean(np.abs(errs))) if errs else None,
        fps=clip.fps,
    )
    if sensor_dir:
        path = os.path.join(sensor_dir, ref.clip.replace("_90", "") + ".csv")
        if os.path.exists(path):
            _, roms = sensor_strides(read_sensor(path))
            row["sensor_thigh_rom"] = float(np.median(roms)) if len(roms) >= 3 else None
    return row


def _dist(v: pd.Series) -> dict[str, Any] | None:
    v = v.dropna()
    if v.empty:
        return None
    return {
        "n": int(len(v)),
        "median": round(float(v.median()), 2),
        "iqr": [round(float(v.quantile(0.25)), 2), round(float(v.quantile(0.75)), 2)],
    }


def summarise(df: pd.DataFrame) -> dict[str, Any]:
    """Pooled, and per role: PLANTED was chosen on the tuning clips, so the test clips are the check."""
    out = _summarise(df)
    out["by_role"] = {role: _summarise(df[df.role == role]) for role in ("tuning", "test")}
    for part in out["by_role"].values():
        part.pop("generated", None)
    return out


def _summarise(df: pd.DataFrame) -> dict[str, Any]:
    acc = df[df.accepted]
    avail = acc[acc.strides >= 3]
    ms = 1000 / acc.fps.median() if len(acc) else math.nan
    matched = acc.dropna(subset=["strike_abs_error_frames_mean"])
    out: dict[str, Any] = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "clips": int(len(df)),
        "accepted": int(len(acc)),
        "with_three_label_free_strides": int(len(avail)),
        "labelled_per_leg_shown": int(acc.legs_told_apart.sum()),
        "strike_timing": {
            "strides": int(acc.strikes.sum()),
            "matched_to_a_reference_strike": int(acc.strikes_matched.sum()),
            "bias_ms_median_of_clips": round(float(matched.strike_error_frames_median.median() * ms), 1),
            "mae_ms_mean_of_clips": round(float(matched.strike_abs_error_frames_mean.mean() * ms), 1),
        },
        "distributions": {m: _dist(avail[m]) for m in METRICS},
    }
    if "sensor_thigh_rom" in df:
        d = avail.dropna(subset=["sensor_thigh_rom", "thigh_rom"])
        e = d.thigh_rom - d.sensor_thigh_rom
        out["thigh_rom_vs_sensor"] = {
            "n": int(len(d)),
            "bias_deg": round(float(e.mean()), 1) if len(d) else None,
            "mae_deg": round(float(e.abs().mean()), 1) if len(d) else None,
            "r": round(float(np.corrcoef(d.thigh_rom, d.sensor_thigh_rom)[0, 1]), 2) if len(d) > 2 else None,
            "median_ours": round(float(d.thigh_rom.median()), 1) if len(d) else None,
            "median_sensor": round(float(d.sensor_thigh_rom.median()), 1) if len(d) else None,
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--landmarks", nargs="+", required=True)
    p.add_argument("--sensor", default=None, help="directory of the thigh-sensor files (optional)")
    p.add_argument("--out", default=os.path.join(HERE, "results"))
    args = p.parse_args()
    rows = []
    for ref in load_reference():
        clip = load_clip(ref.clip, args.landmarks, None)
        if clip is not None:
            rows.append(evaluate_clip(ref, clip, args.sensor))
    df = pd.DataFrame(rows)
    os.makedirs(args.out, exist_ok=True)
    df.to_csv(os.path.join(args.out, "kinematics_clips.csv"), index=False)
    summary = summarise(df)
    with open(os.path.join(args.out, "kinematics.json"), "w") as f:
        json.dump(summary, f, indent=1)
        f.write("\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
