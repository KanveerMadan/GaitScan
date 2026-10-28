"""Pose landmarks -> quality gate -> steady passes -> events -> measurements (ADR-006)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import cv2

from gaitcore import quality
from gaitcore.calibration import Calibration
from gaitcore.clip import Clip
from gaitcore.gait import leg_length, measure_passes, measure_walk
from gaitcore.result import (
    WALK,
    AnalysisResult,
    curves_from_walk,
    metrics_from_walk,
    notes_from_walk,
    pass_results,
    pass_variability,
)
from gaitcore.segments import steady_segments
from gaitcore.signals import build_tracks


class UnsupportedTest(ValueError):
    """A test type with no validated analysis (only TESTS can be run)."""


def _rejected(r: quality.Rejection, q: dict[str, object]) -> AnalysisResult:
    return AnalysisResult(status="rejected", rejection=r, quality=q)


def analyse(clip: Clip, calibration: Calibration | None = None, test: str = WALK) -> AnalysisResult:
    """Checks every test needs (length, frame rate, one upright person), then the test's own."""
    run_test = TESTS.get(test)
    if run_test is None:
        raise UnsupportedTest(test)
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
        result = _rejected(r, q)
    else:
        q["frames_with_pose"] = int(quality.has_pose(clip).sum())
        r = quality.people(clip) or quality.orientation(clip)
        result = _rejected(r, q) if r else run_test(clip, calibration, q)
    result.test = test
    return result


def _analyse_walk(clip: Clip, calibration: Calibration | None, q: dict[str, object]) -> AnalysisResult:
    """Overground walk filmed side-on: steady passes across the frame (ADR-006)."""
    q["feet_visible_fraction"] = round(quality.feet_fraction(clip), 3)
    r = quality.feet(clip)
    if r:
        return _rejected(r, q)

    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    segments = steady_segments(clip, tracks, leg_px) if math.isfinite(leg_px) else []
    ratio = quality.view_ratio(clip, tracks, segments)
    q["view_ratio"] = round(ratio, 3) if math.isfinite(ratio) else None
    q["passes"] = len({s.pass_index for s in segments})
    steady_frames = sum(s.end - s.start for s in segments)
    q["steady_walking_s"] = round(steady_frames / clip.fps, 2)
    q["usable_frame_fraction"] = round(steady_frames / clip.n_frames, 3)
    convergence = quality.path_convergence(clip, tracks, leg_px) if math.isfinite(leg_px) else math.nan
    q["path_convergence_deg"] = round(convergence, 1) if math.isfinite(convergence) else None
    r = quality.side_view(ratio) or quality.path_view(convergence)
    if r:
        return _rejected(r, q)

    walk = measure_walk(clip, segments, calibration, tracks=tracks)
    q["steps_detected"] = walk.step_count
    q["strides"] = {"left": len(walk.stride_times["L"]), "right": len(walk.stride_times["R"])}
    cv = quality.step_time_cv(walk.contact_step_times)
    q["step_time_cv"] = round(cv, 3) if math.isfinite(cv) else None
    r = quality.enough_walking(walk.step_count, steady_frames / clip.fps) or quality.regular_steps(
        walk.contact_step_times
    )
    if r:
        return _rejected(r, q)
    direction = {s.pass_index: s.direction for s in segments}
    walks = measure_passes(clip, segments, calibration, tracks=tracks)
    passes = pass_results(
        [(k, direction[k], w) for k, w in zip(sorted(direction), walks, strict=True)], quality.MIN_STEPS
    )
    return AnalysisResult(
        status="accepted",
        metrics=metrics_from_walk(walk),
        quality=q,
        notes=notes_from_walk(walk),
        passes=passes,
        pass_variability=pass_variability(passes),
        curves=curves_from_walk(walk),
    )


# A test type is added here only with its own accuracy check (Plan V3 Phase 3). A walk on a
# treadmill isn't the overground walk: it never crosses the frame, so steady_segments finds no pass
# and path_view rejects it as view_unconfirmed. Treadmill mode needs its own pass finder and
# side-view check, checked on treadmill clips; measure_walk already times a walker in place.
TESTS: dict[str, Callable[[Clip, Calibration | None, dict[str, object]], AnalysisResult]] = {
    WALK: _analyse_walk,
}


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frames: int
    width: int
    height: int

    @property
    def duration_s(self) -> float:
        return self.frames / self.fps


def probe(path: str) -> VideoInfo:
    """Container metadata, without decoding. Raises VideoReadError for unreadable files."""
    from gaitcore.landmarks import VideoReadError

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError(f"Cannot open video: {path}")
    info = VideoInfo(
        fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
        frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
    )
    cap.release()
    if info.fps <= 0 or info.frames <= 0:
        raise VideoReadError(f"No frames or frame rate in: {path}")
    return info


def precheck(info: VideoInfo, test: str = WALK) -> AnalysisResult | None:
    """Reject too-short or low-frame-rate files before the pose model runs on them."""
    q: dict[str, object] = {
        "fps": round(info.fps, 2),
        "duration_s": round(info.duration_s, 2),
        "frames_total": info.frames,
    }
    r = quality.too_short(info.duration_s) or quality.low_frame_rate(info.fps)
    if not r:
        return None
    result = _rejected(r, q)
    result.test = test
    return result


def analyse_video(path: str, calibration: Calibration | None = None, test: str = WALK) -> AnalysisResult:
    from gaitcore.landmarks import extract_clip

    if test not in TESTS:
        raise UnsupportedTest(test)
    info = probe(path)
    early = precheck(info, test)
    if early:
        return early
    if calibration is not None:
        calibration.check(info.width, info.height)
    return analyse(extract_clip(path), calibration, test)
