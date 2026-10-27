"""Degradation curves on LJMU (Plan V3 Phase 3.2): how each metric's error grows as the video gets worse.

Every clip in ljmu_reference.csv whose original video is accepted is re-analysed after each
degradation below: the frames are altered, the pinned pose model runs on them
(landmarks.clip_from_frames, as in the app), then gaitcore.pipeline.analyse. Cadence and step time are
scored against the same reference strikes as evaluate.py. Camera yaw can't be simulated from a 2D
video; LJMU filmed every walk from 90 and 45 deg at once, so the 45 deg clip of the same walk is the
yaw point (cached landmarks, no re-extraction).

Degradations (level 0 = original):
- resolution: long side scaled down to the given pixels (INTER_AREA);
- fps: resampled to the given frame rate by taking the nearest original frame (a 24 fps phone);
- compression: every frame JPEG-encoded at the given quality (a proxy for heavy video compression);
- low_light: intensity x gain, then Gaussian sensor noise (SD in 8-bit levels), clipped;
- roll: frame rotated by the given degrees about its centre.

Outputs (--out): degradation_runs.csv (one row per clip x degradation, with the quality features
the reliability model uses) and degradation_summary.json (per degradation and level: acceptance and
cadence / step-time error statistics). Runs already in degradation_runs.csv are skipped, so an
interrupted run can resume. Several workers (e.g. one per degradation, in Docker: MediaPipe needs the
Linux image on macOS) write separate files; --merge combines them.
"""

import argparse
import csv
import json
import math
import os
from collections.abc import Callable, Iterator
from typing import Any

import cv2
import numpy as np
from cv2.typing import MatLike

from evaluation.evaluate import HERE, Reference, error_stats, evaluate_clip, load_clip, load_reference
from gaitcore.clip import Clip
from gaitcore.landmarks import clip_from_frames

LEVELS: dict[str, list[float]] = {
    "resolution": [640, 480, 320],
    "fps": [25, 24, 15],
    "compression": [20, 10, 5],
    "low_light": [0.3, 0.2, 0.1],
    "roll": [-10, 5, 15],
}
LIGHT_NOISE = {0.5: 3.0, 0.3: 5.0, 0.2: 6.0, 0.1: 8.0}


def frames(path: str) -> Iterator[MatLike]:
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        while True:
            ok, f = cap.read()
            if not ok:
                return
            yield f
    finally:
        cap.release()


def alter(kind: str, level: float, seed: int) -> Callable[[MatLike], MatLike]:
    rng = np.random.default_rng(seed)
    if kind == "resolution":

        def f(fr: MatLike) -> MatLike:
            h, w = fr.shape[:2]
            s = level / max(h, w)
            return cv2.resize(fr, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else fr

    elif kind == "compression":

        def f(fr: MatLike) -> MatLike:
            ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, int(level)])
            out = cv2.imdecode(buf, cv2.IMREAD_COLOR) if ok else None
            return fr if out is None else out

    elif kind == "low_light":
        sd = LIGHT_NOISE[level]

        def f(fr: MatLike) -> MatLike:
            x = np.asarray(fr, dtype=np.float32) * level + np.asarray(
                rng.normal(0, sd, fr.shape), dtype=np.float32
            )
            return np.clip(x, 0, 255).astype(np.uint8)

    elif kind == "roll":

        def f(fr: MatLike) -> MatLike:
            h, w = fr.shape[:2]
            m = cv2.getRotationMatrix2D((w / 2, h / 2), level, 1.0)
            return cv2.warpAffine(fr, m, (w, h))

    else:
        raise ValueError(kind)
    return f


def degraded_clip(path: str, kind: str, level: float, fps: float, seed: int) -> Clip | None:
    if kind == "fps":  # level < fps: keep the frame nearest each new frame time, streaming
        total = sum(1 for _ in frames(path))
        keep = {min(total - 1, round(i * fps / level)) for i in range(math.floor(total / fps * level))}
        return clip_from_frames((fr for i, fr in enumerate(frames(path)) if i in keep), level)
    f = alter(kind, level, seed)
    return clip_from_frames((f(fr) for fr in frames(path)), fps)


def features(row: dict[str, Any], clip: Clip, quality: dict[str, Any]) -> dict[str, Any]:
    """Quality features of one analysis, for the reliability model (all computed without a reference)."""
    lm = clip.landmarks
    vis = lm[[f"lm{i}_vis" for i in (23, 24, 25, 26, 27, 28, 29, 30)]].to_numpy(dtype=float)
    x = lm[[f"lm{i}_x" for i in (27, 28, 29, 30)]].to_numpy(dtype=float) * clip.width
    jitter = np.nanmedian(np.abs(np.diff(x, n=2, axis=0)))  # px per frame^2: tracking noise
    keys = (
        "fps",
        "frames_with_pose",
        "frames_total",
        "feet_visible_fraction",
        "view_ratio",
        "path_convergence_deg",
        "steady_walking_s",
        "steps_detected",
        "step_time_cv",
        "usable_frame_fraction",
    )
    return {
        **row,
        **{f"q_{k}": quality.get(k) for k in keys},
        "q_height_px": clip.height,
        "q_mean_leg_visibility": round(float(np.nanmean(vis)), 4),
        "q_heel_jitter_px": round(float(jitter), 3) if math.isfinite(jitter) else None,
    }


def run_one(ref: Reference, clip: Clip | None, kind: str, level: float, orig_fps: float) -> dict[str, Any]:
    base = {"clip": ref.clip, "participant": ref.participant, "role": ref.role, "kind": kind, "level": level}
    if clip is None:
        return {**base, "status": "rejected", "rejection": "no_frames"}
    # Reference strikes are original frame numbers: map the clip to the original frame clock.
    scaled = ref if clip.fps == orig_fps else _rescaled(ref, clip.fps / orig_fps)
    row = evaluate_clip(scaled, clip)
    from gaitcore.pipeline import analyse

    q = analyse(clip).quality
    return features({**base, **{k: v for k, v in row.items() if k not in base}}, clip, q)


def _rescaled(ref: Reference, factor: float) -> Reference:
    return Reference(
        ref.clip, ref.participant, ref.role, ref.source, [round(s * factor) for s in ref.strikes]
    )


def _count(codes: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in codes:
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items()))


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ["original", *LEVELS, "yaw"]:
        for level in sorted({float(r["level"]) for r in rows if r["kind"] == kind}):
            sel = [r for r in rows if r["kind"] == kind and float(r["level"]) == level]
            acc = [r for r in sel if r["status"] == "accepted" and r.get("cadence_error") not in (None, "")]
            out.setdefault(kind, {})[str(level)] = {
                "clips": len(sel),
                "accepted": sum(r["status"] == "accepted" for r in sel),
                "rejections": _count(r["rejection"] for r in sel if r["status"] != "accepted"),
                "cadence_steps_per_min": error_stats([float(r["cadence_error"]) for r in acc]),
                "step_time_ms": error_stats([float(r["step_time_error_ms"]) for r in acc]),
            }
    return out


def merge(paths: list[str]) -> list[dict[str, Any]]:
    """Runs from several workers (each a degradation_runs.csv), earliest file first: one row per
    (clip, kind, level), and for each degradation one clip per participant (the earliest file's)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()
    clip_for: dict[tuple[str, str], str] = {}
    for path in paths:
        with open(path) as f:
            for r in csv.DictReader(f):
                key = (r["clip"], r["kind"], float(r["level"]))
                owner = clip_for.setdefault((r["participant"], r["kind"]), r["clip"])
                if key in seen or owner != r["clip"]:
                    continue
                seen.add(key)
                rows.append(r)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--landmarks", nargs="+", required=True)
    ap.add_argument("--videos", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--kinds", nargs="+", default=list(LEVELS))
    ap.add_argument("--per-participant", type=int, default=1, help="clips per participant (first by name)")
    ap.add_argument("--merge", nargs="+", help="merge these runs files (earliest first) into --out instead")
    args = ap.parse_args()
    if args.merge:
        rows = merge(args.merge)
        os.makedirs(args.out, exist_ok=True)
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with open(os.path.join(args.out, "degradation_runs.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(args.out, "degradation_summary.json"), "w") as f:
            json.dump(summarise(rows), f, indent=1)
        return
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "degradation_runs.csv")
    done: list[dict[str, Any]] = list(csv.DictReader(open(path))) if os.path.exists(path) else []
    seen = {(r["clip"], r["kind"], float(r["level"])) for r in done}
    new: list[dict[str, Any]] = []

    def save() -> None:
        rows = done + new
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    per: dict[int, int] = {}
    for ref in load_reference():
        if per.get(ref.participant, 0) >= args.per_participant:
            continue
        clip = load_clip(ref.clip, args.landmarks, None)
        video = os.path.join(args.videos, f"{ref.clip}.mp4")
        if clip is None or not os.path.exists(video):
            continue
        base = run_one(ref, clip, "original", 0, clip.fps)
        if base["status"] != "accepted":
            continue
        per[ref.participant] = per.get(ref.participant, 0) + 1
        todo = [("original", 0.0)] + [(k, float(lv)) for k in args.kinds for lv in LEVELS[k]]
        side45 = load_clip(ref.clip[:-3] + "_45", args.landmarks, None)
        if side45 is not None:
            todo.append(("yaw", 45.0))
        for kind, level in todo:
            if (ref.clip, kind, level) in seen:
                continue
            if kind == "original":
                row = base
            elif kind == "yaw":
                assert side45 is not None
                row = run_one(ref, side45, "yaw", 45, clip.fps)
            else:
                row = run_one(
                    ref, degraded_clip(video, kind, level, clip.fps, ref.participant), kind, level, clip.fps
                )
            new.append(row)
            print(
                ref.clip,
                kind,
                level,
                row["status"],
                row.get("rejection") or row.get("cadence_error"),
                flush=True,
            )
        save()
    rows = done + new
    with open(os.path.join(args.out, "degradation_summary.json"), "w") as f:
        json.dump(summarise(rows), f, indent=1)


if __name__ == "__main__":
    main()
