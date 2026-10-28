"""Accuracy check on LJMU side-view walks (Plan V3 Phase 3): `make evaluate`.

Data: LJMU 360 Degree Gait Capture, Topham et al. 2023, Scientific Data 10:320, CC BY 4.0
(https://opendata.ljmu.ac.uk/id/eprint/133/). Videos and landmarks are never committed; only the
reference strike frames (ljmu_reference.csv) and the results are.

For every clip in ljmu_reference.csv: the pipeline's result (gaitcore.pipeline.analyse) on its
landmarks, and the reference cadence and step time from the reference heel strikes inside the
pipeline's steady walking (first to last steady frame). Reference sources (column `source`):
- visual: heel strikes AI-annotated from the video frames and cross-checked against an independent
  pose model (RTMPose) or the thigh IMU; never human-labelled;
- visual_coarse: AI-annotated on every-3rd-frame contact sheets (cadence to ~1 step/min), used to
  settle clips where RTMPose and the pipeline disagreed by > 5 steps/min;
- rtmpose: RTMPose-x footprint strikes, an independent pose model (on the visual clips, ~2 steps/min
  from the visual count: an occasional extra or missed footprint). Footprints closer than half the
  median interval are merged first.
Column `role`: tuning = the reference was seen while a threshold was chosen (optimistic);
test = never seen before this check.

Outputs (--out): ljmu_clips.csv (one row per clip) and ljmu_summary.json (per role and pooled:
acceptance, rejection reasons, and per metric the error statistics).

Landmarks come from --landmarks directories (<clip>.csv.gz + <clip>.json, as extract_clip gives);
with --videos, missing ones are extracted from <videos>/<clip>.mp4 with the pinned pose model and
saved to the first --landmarks directory. Speed and step length aren't checked: the clips don't show
the start or end of the 8 m walk, so there's no distance reference. Knee angles aren't checked: no
knee-angle reference (Phase 8).
"""

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from gaitcore import __version__ as gaitcore_version
from gaitcore.clip import Clip
from gaitcore.gait import leg_length
from gaitcore.pipeline import analyse, walking
from gaitcore.result import model_info
from gaitcore.signals import build_tracks

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(HERE, "ljmu_reference.csv")
MIN_REFERENCE_STRIKES = 3  # two steps
ROLES = ("tuning", "test")
NOTES = [
    "test clips: the 21 accepted ones among 102 side-view clips never used before (2026-10-26), so their "
    "acceptance is 100% by construction; they share participants with the tuning clips",
    "where the pipeline and RTMPose disagreed by > 5 steps/min the strikes were counted visually "
    "(visual_coarse): 8 tuning and 2 test clips; in both test clips RTMPose was wrong",
    "stride time, step length, walking speed and knee angles are not checked here (see evaluate.py)",
]


@dataclass(frozen=True)
class Reference:
    clip: str
    participant: int
    role: str
    source: str
    strikes: list[int]


def load_reference(path: str = REFERENCE) -> list[Reference]:
    with open(path) as f:
        return [
            Reference(
                r["clip"],
                int(r["participant"]),
                r["role"],
                r["source"],
                [int(x) for x in r["strike_frames"].split()],
            )
            for r in csv.DictReader(f)
        ]


def merge_close(strikes: list[int]) -> list[int]:
    """Drop strikes closer than half the median interval to the previous kept one."""
    if len(strikes) < 3:
        return strikes
    half = 0.5 * float(np.median(np.diff(strikes)))
    kept = [strikes[0]]
    for s in strikes[1:]:
        if s - kept[-1] >= half:
            kept.append(s)
    return kept


def reference_step_time(ref: Reference, first: int, last: int, fps: float) -> float:
    """Mean step time (s) from the reference strikes in [first, last]; NaN with too few."""
    s = [x for x in ref.strikes if first <= x <= last]
    if ref.source == "rtmpose":
        s = merge_close(s)
    if len(s) < MIN_REFERENCE_STRIKES:
        return math.nan
    return (s[-1] - s[0]) / (len(s) - 1) / fps


def load_clip(name: str, landmark_dirs: list[str], videos: str | None) -> Clip | None:
    for d in landmark_dirs:
        if os.path.exists(os.path.join(d, f"{name}.json")):
            with open(os.path.join(d, f"{name}.json")) as f:
                meta = json.load(f)
            lm = pd.read_csv(os.path.join(d, f"{name}.csv.gz"))
            if "p1_hip_in_p0" in lm:  # a dump with raw pose counts: apply landmarks.count_people's rule
                lm.loc[(lm["n_poses"] == 2) & (lm["p1_hip_in_p0"] == 1), "n_poses"] = 1
            return Clip(lm, meta["fps"], meta["width"], meta["height"])
    video = os.path.join(videos, f"{name}.mp4") if videos else None
    if not video or not os.path.exists(video):
        return None
    from gaitcore.landmarks import extract_clip

    clip = extract_clip(video)
    out = landmark_dirs[0]
    os.makedirs(out, exist_ok=True)
    clip.landmarks.to_csv(os.path.join(out, f"{name}.csv.gz"), index=False)
    with open(os.path.join(out, f"{name}.json"), "w") as f:
        json.dump({"fps": clip.fps, "width": clip.width, "height": clip.height}, f)
    return clip


def evaluate_clip(ref: Reference, clip: Clip) -> dict[str, Any]:
    r = analyse(clip)
    row: dict[str, Any] = {
        "clip": ref.clip,
        "participant": ref.participant,
        "role": ref.role,
        "source": ref.source,
        "status": r.status,
        "rejection": r.rejection.code if r.rejection else "",
    }
    if not r.accepted:
        return row
    tracks = build_tracks(clip)
    segs = walking(clip, tracks, leg_length(tracks)).segments
    first, last = segs[0].start, segs[-1].end - 1
    ref_t = reference_step_time(ref, first, last, clip.fps)
    cadence = r.metrics["cadence"]["value"]
    step = r.metrics["step_time"]["value"]
    row.update(
        window_first=first,
        window_last=last,
        steps=r.quality["steps_detected"],
        per_leg_shown=any(v is not None for v in r.metrics["peak_knee_flexion"].values()),
        cadence=cadence,
        step_time=step,
        ref_cadence=round(60 / ref_t, 2) if math.isfinite(ref_t) else None,
        ref_step_time=round(ref_t, 4) if math.isfinite(ref_t) else None,
    )
    if math.isfinite(ref_t):
        row["cadence_error"] = round(cadence - 60 / ref_t, 2)
        row["step_time_error_ms"] = round((step - ref_t) * 1000, 1)
    return row


def error_stats(errors: list[float]) -> dict[str, Any]:
    e = np.asarray(errors, dtype=float)
    if not len(e):
        return {"n": 0}
    a = np.abs(e)
    sd = float(np.std(e, ddof=1)) if len(e) >= 2 else None
    bias = float(np.mean(e))
    out: dict[str, Any] = {
        "n": len(e),
        "mae": round(float(np.mean(a)), 2),
        "rmse": round(float(np.sqrt(np.mean(e**2))), 2),
        "bias": round(bias, 2),
        "sd": None if sd is None else round(sd, 2),
        "p95_abs": round(float(np.percentile(a, 95)), 2),
        "max_abs": round(float(np.max(a)), 2),
    }
    if sd is not None:  # Bland-Altman 95% limits of agreement
        out["limits_of_agreement"] = [round(bias - 1.96 * sd, 2), round(bias + 1.96 * sd, 2)]
    return out


def repeatability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Two walks of the same person in the same session (same participant and experiment, both
    accepted): the spread of their difference. mdc_95 = 1.96 x SD of the differences, the change a
    repeat walk exceeds only 5% of the time. Same-session only: day-to-day variation isn't in it."""
    import itertools
    import re

    groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for r in rows:
        m = re.match(r"P\d+_E(\d)T", r["clip"])
        if r["status"] == "accepted" and m:
            groups.setdefault((r["participant"], m.group(1)), []).append(r)
    pairs = [
        (a, b)
        for g in groups.values()
        for a, b in itertools.combinations(sorted(g, key=lambda r: r["clip"]), 2)
    ]

    def stats(diffs: list[float]) -> dict[str, Any]:
        d = np.asarray(diffs, dtype=float)
        sd = float(np.std(d, ddof=1)) if len(d) >= 2 else None
        return {
            "mean_abs_diff": round(float(np.mean(np.abs(d))), 2) if len(d) else None,
            "sd_diff": None if sd is None else round(sd, 2),
            "mdc_95": None if sd is None else round(1.96 * sd, 2),
        }

    return {
        "pairs": len(pairs),
        "participants": len({a["participant"] for a, _ in pairs}),
        "cadence_steps_per_min": stats([a["cadence"] - b["cadence"] for a, b in pairs]),
        "step_time_ms": stats([(a["step_time"] - b["step_time"]) * 1000 for a, b in pairs]),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(sel: list[dict[str, Any]]) -> dict[str, Any]:
        accepted = [r for r in sel if r["status"] == "accepted"]
        rejections: dict[str, int] = {}
        for r in sel:
            if r["rejection"]:
                rejections[r["rejection"]] = rejections.get(r["rejection"], 0) + 1
        with_ref = [r for r in accepted if r.get("cadence_error") is not None]
        return {
            "clips": len(sel),
            "participants": len({r["participant"] for r in sel}),
            "accepted": len(accepted),
            "rejections": dict(sorted(rejections.items())),
            "accepted_without_reference": len(accepted) - len(with_ref),
            "per_leg_values_shown": sum(1 for r in accepted if r["per_leg_shown"]),
            "cadence_steps_per_min": error_stats([r["cadence_error"] for r in with_ref]),
            "step_time_ms": error_stats([r["step_time_error_ms"] for r in with_ref]),
        }

    return {"all": block(rows), **{role: block([r for r in rows if r["role"] == role]) for role in ROLES}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--landmarks", nargs="+", required=True, help="directories of <clip>.csv.gz + <clip>.json"
    )
    ap.add_argument("--videos", help="directory of <clip>.mp4, for clips without landmarks")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    args = ap.parse_args()

    rows, missing = [], []
    for ref in load_reference():
        clip = load_clip(ref.clip, args.landmarks, args.videos)
        if clip is None:
            missing.append(ref.clip)
            continue
        rows.append(evaluate_clip(ref, clip))
    if missing:
        raise SystemExit(
            f"No landmarks or video for {len(missing)} clips, e.g. {missing[:3]} (make fetch-ljmu)"
        )

    os.makedirs(args.out, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(args.out, "ljmu_clips.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "dataset": "LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0), 90 deg view",
        "reference": "heel strikes: AI-annotated + cross-checked (visual), or RTMPose-x footprints; see evaluate.py",
        "notes": NOTES,
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "pipeline_version": gaitcore_version,
        "model": model_info(),
        **summarise(rows),
        "repeatability": repeatability(rows),
    }
    with open(os.path.join(args.out, "ljmu_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    s = summary["all"]
    print(
        f"{s['clips']} clips, {s['accepted']} accepted; cadence MAE {s['cadence_steps_per_min'].get('mae')} "
        f"steps/min (n {s['cadence_steps_per_min']['n']}); test: {summary['test']['cadence_steps_per_min']}"
    )


if __name__ == "__main__":
    main()
