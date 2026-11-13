"""Left/right check against LJMU's right-thigh goniometer (Plan V3 Phase 11, BE-A1): `make leg-labels`.

Data: LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0). In tasks 1
and 2 a MOTI digital goniometer (an IMU, 84 Hz) sits on the right thigh just above the knee. The files
(`P<p>_E<e>T<t>.csv`, fetched by `python -m evaluation.fetch_ljmu --imu`) hold quaternions q0..q3, a
`MotionDeg` angle and raw inertial data, with a timestamp.

Questions:
1. Can the sensor say which leg is the right one? Only if it is aligned in time with the side-view
   clip to well under a quarter stride: left and right thighs trace the same curve half a stride apart,
   so a misalignment of half a stride swaps them. Tested at the start-aligned lag (0) and at the lag that
   aligns movement onset (sensor rotation rate vs pelvis speed), both leg-independent.
2. Without alignment: per recording, the sensor's median stride time and per-stride thigh range of
   motion against the pipeline's pooled stride (2 x step time), labelled per-side strides and per-side
   thigh range. The sensor recording and the clip's steady walking aren't the same stretch of walking,
   so this is a coarse, average-level reference.

Outputs (--out): leg_labels_clips.csv (one row per clip) and leg_labels.json (summary). The findings are
written up in docs/validation/leg-labels.md.
"""

import argparse
import glob
import json
import math
import os
from datetime import UTC, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from gaitcore.angles import thigh_angle
from gaitcore.dsp import find_peaks
from gaitcore.gait import leg_length, measure_walk
from gaitcore.pipeline import analyse, walking
from gaitcore.result import legs_told_apart
from gaitcore.signals import build_tracks

HERE = os.path.dirname(os.path.abspath(__file__))
STRIDE_S = (0.7, 2.0)  # a walking stride; outside this a peak pair is a detection error
PEAK_PROMINENCE_DEG = 8.0  # thigh flexion peaks rise ~40 deg per stride; 8 deg rejects ripple
ONSET_SENSOR_RAD_S = 0.5  # rotation rate that counts as moving
ONSET_PELVIS_LEGS_S = 0.3  # pelvis speed, leg lengths per second, that counts as moving
BEST_LAG_S = 2.0  # offsets searched for the best match

Array = npt.NDArray[np.float64]


def _qmul(a: Array, b: Array) -> Array:
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.c_[
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ]


def sagittal_angle(rec: pd.DataFrame) -> Array:
    """The thigh's signed swing angle in degrees: each orientation relative to the median one, as a
    rotation vector, projected on the main rotation axis (the thigh swings about one axis when walking).
    Flexion is made positive from the timing of a stride: the thigh flexes during swing (~40% of the
    stride) and extends during stance (~60%), so the rising half of the signal is the shorter one.
    Offset-free (no standing pose). (MotionDeg isn't used: it is unsigned and reads about half the range.)"""
    q = rec[["q0", "q1", "q2", "q3"]].to_numpy(float)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    ref = np.median(q, axis=0)
    ref /= np.linalg.norm(ref)
    rel = _qmul(np.tile([ref[0], -ref[1], -ref[2], -ref[3]], (len(q), 1)), q)
    rel[rel[:, 0] < 0] *= -1
    ang = 2 * np.arccos(np.clip(rel[:, 0], -1, 1))
    axis = rel[:, 1:] / np.maximum(np.sin(ang / 2), 1e-9)[:, None]
    rv = axis * ang[:, None]
    u = np.linalg.svd(rv - rv.mean(0), full_matrices=False)[2][0]
    a = np.degrees(rv @ u)
    rising = float(np.mean(np.diff(a) > 0))
    return a if rising <= 0.5 else -a


def sensor_strides(rec: pd.DataFrame) -> tuple[list[float], list[float]]:
    """Stride times (s) between flexion peaks, and each stride's range (deg), without the first and last
    stride when there are five or more (starting and stopping)."""
    t = rec["Timestamp"].to_numpy(float)
    if len(t) < 3:
        return [], []
    a = sagittal_angle(rec)
    fs = 1 / float(np.median(np.diff(t)))
    pk = find_peaks(a, distance=max(1, int(STRIDE_S[0] * fs)), prominence=PEAK_PROMINENCE_DEG)
    pairs = [(i, j) for i, j in zip(pk, pk[1:], strict=False) if STRIDE_S[0] <= t[j] - t[i] <= STRIDE_S[1]]
    if len(pairs) >= 5:
        pairs = pairs[1:-1]
    return [float(t[j] - t[i]) for i, j in pairs], [float(np.ptp(a[i : j + 1])) for i, j in pairs]


def read_sensor(path: str) -> pd.DataFrame:
    rec = pd.read_csv(path, skiprows=2)
    return rec.dropna(subset=["Timestamp", "q0", "q1", "q2", "q3"]).reset_index(drop=True)


def _median(v: list[float]) -> float:
    return float(np.median(v)) if len(v) else math.nan


def sync_test(clip: Any, tracks: Any, segs: list[Any], rec: pd.DataFrame) -> dict[str, Any]:
    """Correlation of each labelled thigh with the sensor at the start-aligned lag and at the
    onset-aligned lag. If either alignment were right, the labelled right thigh would win clearly."""
    t = rec["Timestamp"].to_numpy(float)
    a = sagittal_angle(rec)
    gyro = np.sqrt((rec[["gyrX", "gyrY", "gyrZ"]].to_numpy(float) ** 2).sum(1)) if "gyrX" in rec else None
    lp = leg_length(tracks)
    vx = np.abs(np.gradient(tracks.pelvis[:, 0])) * clip.fps / lp
    onset_video = next(
        (i / clip.fps for i, v in enumerate(vx) if np.isfinite(v) and v > ONSET_PELVIS_LEGS_S), math.nan
    )
    onset_sensor = (
        next((float(ti) for ti, g in zip(t, gyro, strict=False) if g > ONSET_SENSOR_RAD_S), math.nan)
        if gyro is not None
        else math.nan
    )

    def corr(side: str, lag: float) -> float:
        cs = []
        for s in segs:
            f = np.arange(s.start, s.end)
            th = thigh_angle(tracks[(side, "hip")][f], tracks[(side, "knee")][f], s.direction)
            x = np.interp(f / clip.fps + lag, t, a, left=np.nan, right=np.nan)
            ok = np.isfinite(th) & np.isfinite(x)
            if ok.sum() > 20:
                cs.append(float(np.corrcoef(th[ok], x[ok])[0, 1]))
        return float(np.mean(cs)) if cs else math.nan

    lag_onset = onset_sensor - onset_video if math.isfinite(onset_sensor + onset_video) else math.nan
    # The best match within +-BEST_LAG_S, either leg: does the sensor follow the video at all, and
    # at what offset? (An offset that varies by more than half a stride can't tell the legs apart.)
    scan = [
        (corr(side, lag), lag, side)
        for lag in np.arange(-BEST_LAG_S, BEST_LAG_S + 1e-9, 1 / clip.fps)
        for side in "RL"
    ]
    scan = [x for x in scan if math.isfinite(x[0])]
    best = max(scan) if scan else (math.nan, math.nan, "")
    out = {
        "r_R_lag0": corr("R", 0.0),
        "r_L_lag0": corr("L", 0.0),
        "lag_onset_s": lag_onset,
        "best_r": best[0],
        "best_lag_s": best[1],
        "best_side": best[2],
    }
    if math.isfinite(lag_onset):
        out.update(r_R_onset=corr("R", lag_onset), r_L_onset=corr("L", lag_onset))
    return out


def evaluate_recording(name: str, clip: Any, rec: pd.DataFrame) -> dict[str, Any] | None:
    r = analyse(clip)
    if not r.accepted:
        return None
    tracks = build_tracks(clip)
    segs = walking(clip, tracks, leg_length(tracks)).segments
    w = measure_walk(clip, segs, tracks=tracks)
    strides, roms = sensor_strides(rec)
    row: dict[str, Any] = {
        "clip": name,
        "video_s": round(clip.n_frames / clip.fps, 2),
        "sensor_s": round(float(rec["Timestamp"].iloc[-1] - rec["Timestamp"].iloc[0]), 2),
        "legs_told_apart": legs_told_apart(w),
        "sensor_strides": len(strides),
        "sensor_stride_s": _median(strides),
        "sensor_rom_deg": _median(roms),
        "pooled_stride_s": 2 * r.metrics["step_time"]["value"],
        "R_stride_s": _median(w.stride_times["R"]),
        "L_stride_s": _median(w.stride_times["L"]),
        "R_rom_deg": _median(w.hip_excursion["R"]),
        "L_rom_deg": _median(w.hip_excursion["L"]),
    }
    row.update(sync_test(clip, tracks, segs, rec))
    return row


def _errors(df: pd.DataFrame, col: str, ref: str, scale: float = 1.0) -> dict[str, Any]:
    e = (df[col] - df[ref]).dropna() * scale
    if e.empty:
        return {"n": 0}
    return {
        "n": int(len(e)),
        "bias": round(float(e.mean()), 1),
        "mae": round(float(e.abs().mean()), 1),
        "p95_abs": round(float(e.abs().quantile(0.95)), 1),
    }


def summarise(df: pd.DataFrame) -> dict[str, Any]:
    ok = df[df.sensor_strides >= 3]
    told = ok[ok.legs_told_apart]
    sync: dict[str, Any] = {}
    for tag in ("lag0", "onset"):
        d = df.dropna(subset=[f"r_R_{tag}", f"r_L_{tag}"]) if f"r_R_{tag}" in df else df.iloc[0:0]
        sync[tag] = {
            "clips": int(len(d)),
            "labelled_right_matches_better": round(float((d[f"r_R_{tag}"] > d[f"r_L_{tag}"]).mean()), 3)
            if len(d)
            else None,
            "median_r_R": round(float(d[f"r_R_{tag}"].median()), 2) if len(d) else None,
            "median_r_L": round(float(d[f"r_L_{tag}"].median()), 2) if len(d) else None,
        }
    b = df.dropna(subset=["best_r"])
    sync["best_within_2s"] = {
        "clips": int(len(b)),
        "median_r": round(float(b.best_r.median()), 2),
        "iqr_r": [round(float(b.best_r.quantile(q)), 2) for q in (0.25, 0.75)],
        "iqr_lag_s": [round(float(b.best_lag_s.quantile(q)), 2) for q in (0.25, 0.75)],
        "best_is_labelled_right": round(float((b.best_side == "R").mean()), 3),
    }
    rom = {}
    for col in ("R_rom_deg", "L_rom_deg"):
        d = ok[[col, "sensor_rom_deg"]].dropna()
        rom[col] = {
            **_errors(ok, col, "sensor_rom_deg"),
            "r": round(float(np.corrcoef(d[col], d.sensor_rom_deg)[0, 1]), 2) if len(d) > 2 else None,
            "median_ours": round(float(d[col].median()), 1) if len(d) else None,
            "median_sensor": round(float(d.sensor_rom_deg.median()), 1) if len(d) else None,
        }
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "recordings": int(len(df)),
        "with_three_sensor_strides": int(len(ok)),
        "legs_told_apart": int(ok.legs_told_apart.sum()),
        "video_vs_sensor_length_s": {
            "median_abs_diff": round(float((df.video_s - df.sensor_s).abs().median()), 2),
            "max_abs_diff": round(float((df.video_s - df.sensor_s).abs().max()), 2),
        },
        "sync": sync,
        "stride_ms_vs_sensor": {
            "pooled_all": _errors(ok, "pooled_stride_s", "sensor_stride_s", 1000),
            "labelled_right_all": _errors(ok, "R_stride_s", "sensor_stride_s", 1000),
            "pooled_told_apart": _errors(told, "pooled_stride_s", "sensor_stride_s", 1000),
            "labelled_right_told_apart": _errors(told, "R_stride_s", "sensor_stride_s", 1000),
        },
        "thigh_rom_deg_vs_sensor": rom,
    }


def main() -> None:
    from evaluation.evaluate import load_clip

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--landmarks", nargs="+", required=True, help="landmark directories (<clip>.csv.gz + .json)"
    )
    p.add_argument("--sensor", required=True, help="directory of P<p>_E<e>T<t>.csv sensor files")
    p.add_argument("--out", default=os.path.join(HERE, "results"))
    args = p.parse_args()
    rows = []
    for path in sorted(glob.glob(os.path.join(args.sensor, "P*_E*T[12].csv"))):
        name = os.path.basename(path)[:-4] + "_90"
        clip = load_clip(name, args.landmarks, None)
        if clip is None:
            continue
        row = evaluate_recording(name, clip, read_sensor(path))
        if row is not None:
            rows.append(row)
    df = pd.DataFrame(rows)
    os.makedirs(args.out, exist_ok=True)
    df.round(4).to_csv(os.path.join(args.out, "leg_labels_clips.csv"), index=False)
    with open(os.path.join(args.out, "leg_labels.json"), "w") as f:
        json.dump(summarise(df), f, indent=1)
        f.write("\n")
    print(json.dumps(summarise(df), indent=1))


if __name__ == "__main__":
    main()
