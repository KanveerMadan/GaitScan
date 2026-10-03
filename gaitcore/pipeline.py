"""Pose landmarks -> quality gate -> steady passes -> events -> measurements (ADR-006)."""

import math

import cv2

from gaitcore import quality
from gaitcore.calibration import Calibration
from gaitcore.clip import Clip
from gaitcore.gait import leg_length, measure_walk
from gaitcore.result import AnalysisResult, metrics_from_walk
from gaitcore.segments import steady_segments
from gaitcore.signals import build_tracks


def _rejected(r: quality.Rejection, q: dict[str, object]) -> AnalysisResult:
    return AnalysisResult(status="rejected", rejection=r, quality=q)


def analyse(clip: Clip, calibration: Calibration | None = None) -> AnalysisResult:
    q: dict[str, object] = {
        "fps": round(clip.fps, 2),
        "duration_s": round(clip.duration_s, 2),
        "frames_total": clip.n_frames,
        "calibrated": calibration is not None,
    }
    if calibration is not None:
        calibration.check(clip.width, clip.height)  # CalibrationError: a user-facing reason
    r = quality.too_short(clip.duration_s) or quality.low_frame_rate(clip.fps)
    if r:
        return _rejected(r, q)
    pose = quality.has_pose(clip)
    q["frames_with_pose"] = int(pose.sum())
    r = quality.people(clip) or quality.orientation(clip)
    if r:
        return _rejected(r, q)
    q["feet_visible_fraction"] = round(quality.feet_fraction(clip), 3)
    r = quality.feet(clip)
    if r:
        return _rejected(r, q)

    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    segments = steady_segments(clip, tracks, leg_px) if math.isfinite(leg_px) else []
    ratio = quality.view_ratio(clip, tracks, segments)
    q["view_ratio"] = round(ratio, 3) if math.isfinite(ratio) else None
    q["passes"] = len(segments)
    steady_frames = sum(s.end - s.start for s in segments)
    q["steady_walking_s"] = round(steady_frames / clip.fps, 2)
    q["usable_frame_fraction"] = round(steady_frames / clip.n_frames, 3)
    r = quality.side_view(ratio)
    if r:
        return _rejected(r, q)

    walk = measure_walk(clip, segments, calibration, tracks=tracks)
    q["steps_detected"] = len(walk.step_times)
    q["strides"] = {"left": len(walk.stride_times["L"]), "right": len(walk.stride_times["R"])}
    r = quality.enough_walking(len(walk.step_times))
    if r:
        return _rejected(r, q)
    return AnalysisResult(status="accepted", metrics=metrics_from_walk(walk), quality=q)


def analyse_video(path: str, calibration: Calibration | None = None) -> AnalysisResult:
    """Reject too-short or low-frame-rate files before running the pose model on them."""
    from gaitcore.landmarks import VideoReadError, extract_clip

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError(f"Cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if fps <= 0 or frames <= 0:
        raise VideoReadError(f"No frames or frame rate in: {path}")
    q: dict[str, object] = {
        "fps": round(fps, 2),
        "duration_s": round(frames / fps, 2),
        "frames_total": frames,
    }
    r = quality.too_short(frames / fps) or quality.low_frame_rate(fps)
    if r:
        return _rejected(r, q)
    if calibration is not None:
        calibration.check(w, h)
    return analyse(extract_clip(path), calibration)
