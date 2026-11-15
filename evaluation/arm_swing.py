"""Arm swing against LJMU's upper-arm sensor (Plan V3 Phase 11, owner decision D6): `make arm-swing`.

Data: LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0). In tasks 3
and 4 of each experiment the MOTI goniometer (an IMU, 84 Hz) is on the right arm just above the elbow,
so it follows the upper arm. Each task is one 8 m walk past the side camera: a -> b in task 3, b -> a in
task 4, so the right arm faces the camera in one of them and is the far arm in the other.
`python -m evaluation.fetch_ljmu --arm data/ljmu/arm` fetches the sensor files and the side-view clips.

Steps:
1. `extract` (in Docker: MediaPipe aborts on macOS) writes each clip's landmarks as
   <out>/<clip>.csv.gz + .json, as evaluation/evaluate.py's load_clip reads them.
2. `compare` runs the pipeline on each clip and compares, per recording:
   - GaitScan's arm swing as the app shows it (gaitcore.kinematics: the upper arm, shoulder -> elbow,
     against vertical, per stride the range of each arm seen through >= 80% of it, the larger; median over
     strides). Until 2026-11-15 it was shoulder -> wrist (owner decision after this check);
   - the same for shoulder -> wrist, the measure shown before, kept for the record;
   - the sensor's upper-arm swing: the signed swing angle about the main rotation axis
     (evaluation.leg_labels.sagittal_angle), then the median rise or fall between alternating peaks and
     troughs (prominence >= 5 deg), leaving out the first and last (starting and stopping). The thigh
     check's stride-to-stride peaks don't fit the arm: its recordings are short (~4-5 s) and the arm
     signal isn't a clean once-per-stride wave.
   As with the thigh check (docs/validation/kinematics.md) the sensor isn't time-aligned with the clip
   and its recording isn't the same stretch of walking as the clip's steady part, so this is an
   average-level comparison per recording, not frame by frame.

Agreement criteria, set before the comparison was run (2026-11-15): show an error range (about +-MAE,
as for the other angles) only if, over all recordings, the bias is within +-5 deg, the MAE is <= 10 deg
and Pearson's r >= 0.6. Otherwise arm swing stays information only.

Outputs (--out): arm_swing_clips.csv (one row per recording) and arm_swing.json (summary). Written up in
docs/validation/arm-swing.md.
"""

import argparse
import glob
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

CRITERIA = {"bias_abs_max_deg": 5.0, "mae_max_deg": 10.0, "r_min": 0.6}
WRISTS = (15, 16)  # MediaPipe Pose left and right wrist
MIN_SENSOR_SWINGS = 3
SENSOR_PROMINENCE_DEG = 5.0
MIN_STRIDES_UNGATED = 3


def sensor_swing(rec: pd.DataFrame) -> tuple[float | None, int, float | None]:
    """(median swing between alternating extremes, number of swings, median time between peaks)."""
    from scipy.signal import find_peaks

    from evaluation.leg_labels import sagittal_angle

    t = rec["Timestamp"].to_numpy(float)
    if len(t) < 10:
        return None, 0, None
    a = sagittal_angle(rec)
    hi, _ = find_peaks(a, prominence=SENSOR_PROMINENCE_DEG)
    lo, _ = find_peaks(-a, prominence=SENSOR_PROMINENCE_DEG)
    ext = sorted([(int(i), 1) for i in hi] + [(int(i), -1) for i in lo])
    alt: list[tuple[int, int]] = []  # alternating: of two maxima (or minima) in a row keep the larger
    for i, kind in ext:
        if alt and alt[-1][1] == kind:
            if kind * a[i] > kind * a[alt[-1][0]]:
                alt[-1] = (i, kind)
        else:
            alt.append((i, kind))
    alt = alt[1:-1]  # starting and stopping
    swings = [abs(float(a[j] - a[i])) for (i, _), (j, _) in zip(alt, alt[1:], strict=False)]
    peaks = [i for i, kind in alt if kind == 1]
    period = float(np.median(np.diff(t[peaks]))) if len(peaks) >= 2 else None
    if len(swings) < MIN_SENSOR_SWINGS:
        return None, len(swings), period
    return float(np.median(swings)), len(swings), period


def _extract_one(args: tuple[str, str]) -> str:
    video, out = args
    from gaitcore.landmarks import extract_clip

    name = os.path.basename(video)[:-4]
    clip = extract_clip(video)
    clip.landmarks.to_csv(os.path.join(out, f"{name}.csv.gz"), index=False)
    with open(os.path.join(out, f"{name}.json"), "w") as f:
        json.dump({"fps": clip.fps, "width": clip.width, "height": clip.height}, f)
    return name


def extract(videos: str, out: str, workers: int) -> None:
    os.makedirs(out, exist_ok=True)
    todo = [
        (v, out)
        for v in sorted(glob.glob(os.path.join(videos, "*.mp4")))
        if not os.path.exists(os.path.join(out, os.path.basename(v)[:-4] + ".json"))
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, name in enumerate(pool.map(_extract_one, todo), 1):
            print(f"{i}/{len(todo)} {name}", flush=True)


def wrist_line_swing(clip: Any, tracks: Any, strides: list[Any]) -> float | None:
    """Per stride, the range of each shoulder -> wrist line against vertical seen through >= 80% of it,
    the larger; the median over strides: the arm swing shown before 2026-11-15, by the same rules."""
    from gaitcore.kinematics import ARM_DOWN_DEG
    from gaitcore.signals import masked_xy

    per_stride = []
    for s in strides:
        ranges = []
        for side, e in zip(("L", "R"), WRISTS, strict=True):
            v = masked_xy(clip, e) - tracks[(side, "shoulder")]
            a = np.degrees(np.arctan2(v[:, 0] * s.direction, v[:, 1]))
            a = np.where(np.abs(a) <= ARM_DOWN_DEG, a, np.nan)[s.start : s.end + 1]
            if np.isfinite(a).mean() >= 0.8:
                ranges.append(float(np.nanmax(a) - np.nanmin(a)))
        if ranges:
            per_stride.append(max(ranges))
    return float(np.median(per_stride)) if per_stride else None


def compare_one(name: str, landmarks: str, sensor: str) -> dict[str, Any]:
    from evaluation.evaluate import load_clip
    from evaluation.leg_labels import read_sensor
    from gaitcore.gait import leg_length
    from gaitcore.kinematics import measure_kinematics
    from gaitcore.pipeline import analyse, walking
    from gaitcore.signals import build_tracks

    stem = name.replace("_90", "")
    p, e, t = stem[1:].replace("_E", " ").replace("T", " ").split()
    row: dict[str, Any] = {"clip": name, "participant": int(p), "experiment": int(e), "task": int(t)}
    swing, n_swings, period = sensor_swing(read_sensor(os.path.join(sensor, f"{stem}.csv")))
    row.update(
        sensor_swings=n_swings,
        sensor_upper_arm=None if swing is None else round(swing, 2),
        sensor_stride_s=None if period is None else round(period, 3),
    )
    clip = load_clip(name, [landmarks], None)
    if clip is None:
        return {**row, "accepted": None}
    r = analyse(clip)
    row["accepted"] = r.accepted
    row["rejection"] = r.rejection.code if r.rejection else None
    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    segs = walking(clip, tracks, leg_px).segments if math.isfinite(leg_px) else []
    # The accepted walks are what the app would show; without the recording checks (secondary, labelled
    # as such) every clip with >= 3 label-free strides counts.
    k = r.kinematics if r.accepted and r.kinematics is not None else measure_kinematics(clip, segs, tracks)
    if not k.strides:
        return row
    direction = segs[0].direction if segs else None
    arm = k.summary().get("arm_swing_deg")
    step = (r.metrics.get("step_time") or {}).get("value") if r.accepted else None
    row.update(
        strides=len(k.strides),
        # Walking towards image +x the right side faces the camera (docs/validation/leg-identity.md).
        right_arm_near=None if direction is None else bool(direction > 0),
        gaitscan_arm_swing=None if arm is None else round(arm["value"], 2),
        gaitscan_shoulder_wrist=(
            None if (u := wrist_line_swing(clip, tracks, k.strides)) is None else round(u, 2)
        ),
        stride_s=None if step is None else round(2 * step, 3),
    )
    return row


def agreement(ours: pd.Series, sensor: pd.Series) -> dict[str, Any] | None:
    ok = ours.notna() & sensor.notna()
    a, b = ours[ok].to_numpy(float), sensor[ok].to_numpy(float)
    if len(a) < 3:
        return None
    d = a - b
    return {
        "n": int(len(a)),
        "gaitscan_mean": round(float(a.mean()), 1),
        "sensor_mean": round(float(b.mean()), 1),
        "bias": round(float(d.mean()), 1),
        "mae": round(float(np.abs(d).mean()), 1),
        "limits_of_agreement": [round(float(d.mean() - 1.96 * d.std(ddof=1)), 1), round(float(d.mean() + 1.96 * d.std(ddof=1)), 1)],
        "r": round(float(np.corrcoef(a, b)[0, 1]), 2),
    }  # fmt: skip


def passes(a: dict[str, Any] | None) -> bool:
    return bool(
        a
        and abs(a["bias"]) <= CRITERIA["bias_abs_max_deg"]
        and a["mae"] <= CRITERIA["mae_max_deg"]
        and a["r"] >= CRITERIA["r_min"]
    )


def summarise(df: pd.DataFrame) -> dict[str, Any]:
    acc = df[df.accepted == True]  # noqa: E712  (None for clips without landmarks)
    out: dict[str, Any] = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "recordings": int(len(df)),
        "with_landmarks": int(df.accepted.notna().sum()),
        "accepted": int(len(acc)),
        "sensor_usable": int(df.sensor_upper_arm.notna().sum()),
        "criteria": CRITERIA,
    }
    for name, part in (
        ("all", acc),
        ("right_arm_near", acc[acc.right_arm_near == True]),  # noqa: E712
        ("right_arm_far", acc[acc.right_arm_near == False]),  # noqa: E712
    ):
        out[name] = {
            "arm_swing_shown": agreement(part.gaitscan_arm_swing, part.sensor_upper_arm),
            "shoulder_wrist": agreement(part.gaitscan_shoulder_wrist, part.sensor_upper_arm),
        }
    ungated = df[df.strides.fillna(0) >= MIN_STRIDES_UNGATED] if "strides" in df else df.iloc[0:0]
    out["without_recording_checks"] = {
        "recordings": int(len(ungated)),
        "arm_swing_shown": agreement(ungated.gaitscan_arm_swing, ungated.sensor_upper_arm),
        "shoulder_wrist": agreement(ungated.gaitscan_shoulder_wrist, ungated.sensor_upper_arm),
    }
    out["rejections"] = df.rejection.value_counts().to_dict() if "rejection" in df else {}
    stride = agreement(acc.stride_s, acc.sensor_stride_s)
    out["stride_time_check"] = stride  # the sensor recording and the clip: the same walk?
    out["passes"] = {
        "arm_swing_shown": passes(out["all"]["arm_swing_shown"]),
        "shoulder_wrist": passes(out["all"]["shoulder_wrist"]),
    }
    return out


def compare(landmarks: str, sensor: str, out: str, workers: int) -> dict[str, Any]:
    names = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(landmarks, "*.json")))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(compare_one, names, [landmarks] * len(names), [sensor] * len(names)))
    df = pd.DataFrame(rows)
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, "arm_swing_clips.csv"), index=False)
    summary = summarise(df)
    with open(os.path.join(out, "arm_swing.json"), "w") as f:
        json.dump(summary, f, indent=1)
        f.write("\n")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("command", choices=("extract", "compare"))
    p.add_argument("--videos", default="data/ljmu/arm/videos")
    p.add_argument("--landmarks", default="data/ljmu/arm/landmarks")
    p.add_argument("--sensor", default="data/ljmu/arm/imu")
    p.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()
    if args.command == "extract":
        extract(args.videos, args.landmarks, args.workers)
    else:
        s = compare(args.landmarks, args.sensor, args.out, args.workers)
        print(json.dumps(s, indent=1))  # noqa: T201


if __name__ == "__main__":
    main()
