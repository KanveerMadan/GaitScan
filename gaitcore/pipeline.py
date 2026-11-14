"""Pose landmarks -> quality gate -> steady passes -> events -> measurements (ADR-006)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import cv2

from gaitcore import quality
from gaitcore.calibration import Calibration
from gaitcore.clip import Clip
from gaitcore.gait import facing, leg_length, measure_passes, measure_walk, typical_step_s
from gaitcore.kinematics import measure_kinematics
from gaitcore.result import (
    TREADMILL,
    WALK,
    AnalysisResult,
    curves_from_walk,
    metrics_from_treadmill,
    metrics_from_walk,
    notes_from_walk,
    pass_results,
    pass_variability,
)
from gaitcore.segments import (
    SMOOTH_RANGE_S,
    SMOOTH_S,
    Segment,
    in_place_segments,
    steady_segments,
    travelling_s,
)
from gaitcore.signals import Tracks, build_tracks


class UnsupportedTest(ValueError):
    """A test type with no validated analysis (only TESTS can be run)."""


def _rejected(r: quality.Rejection, q: dict[str, object]) -> AnalysisResult:
    return AnalysisResult(status="rejected", rejection=r, quality=q)


def analyse(
    clip: Clip,
    calibration: Calibration | None = None,
    test: str = WALK,
    belt_speed_m_s: float | None = None,
) -> AnalysisResult:
    """Checks every test needs (length, frame rate, one upright person), then the test's own. The
    treadmill test needs the belt speed; the walk ignores it."""
    run_test = TESTS.get(test)
    if run_test is None:
        raise UnsupportedTest(test)
    if test == TREADMILL and belt_speed_m_s is None:
        raise ValueError("the treadmill test needs belt_speed_m_s")
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
        result = _rejected(r, q) if r else run_test(clip, calibration, q, belt_speed_m_s)
    result.test = test
    return result


@dataclass(frozen=True)
class Walking:
    segments: list[Segment]
    window_s: float  # steadiness window: the walker's own step time, within SMOOTH_RANGE_S
    dropped: quality.Dropped


def walking(clip: Clip, tracks: Tracks, leg_px: float) -> Walking:
    """The steady walking a walk is measured on (segments.py), minus the dropped stretches."""
    dropped = quality.dropped_stretches(clip)
    if not math.isfinite(leg_px):
        return Walking([], SMOOTH_S, dropped)
    step = typical_step_s(clip, tracks, leg_px)
    window = SMOOTH_S if step is None else min(max(step, SMOOTH_RANGE_S[0]), SMOOTH_RANGE_S[1])
    return Walking(steady_segments(clip, tracks, leg_px, window, dropped.usable), window, dropped)


def _analyse_walk(
    clip: Clip, calibration: Calibration | None, q: dict[str, object], _belt: float | None = None
) -> AnalysisResult:
    """Overground walk filmed side-on: steady passes across the frame (ADR-006)."""
    q["feet_visible_fraction"] = round(quality.feet_fraction(clip), 3)
    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    w = walking(clip, tracks, leg_px)
    segments = w.segments
    q["steadiness_window_s"] = round(w.window_s, 3)
    q["second_person_s"] = round(w.dropped.second_person_s, 2)
    q["heels_hidden_s"] = round(w.dropped.heels_hidden_s, 2)
    ratio = quality.view_ratio(clip, tracks, segments)
    q["view_ratio"] = round(ratio, 3) if math.isfinite(ratio) else None
    q["passes"] = len({s.pass_index for s in segments})
    steady_frames = sum(s.end - s.start for s in segments)
    q["steady_walking_s"] = round(steady_frames / clip.fps, 2)
    q["usable_frame_fraction"] = round(steady_frames / clip.n_frames, 3)
    convergence = quality.path_convergence(clip, tracks, leg_px) if math.isfinite(leg_px) else math.nan
    q["path_convergence_deg"] = round(convergence, 1) if math.isfinite(convergence) else None
    r = quality.side_view(ratio) or quality.name_the_cause(quality.path_view(convergence), w.dropped)
    if r:
        return _rejected(r, q)

    walk = measure_walk(clip, segments, calibration, tracks=tracks)
    q["steps_detected"] = walk.step_count
    q["strides"] = {"left": len(walk.stride_times["L"]), "right": len(walk.stride_times["R"])}
    cv = quality.step_time_cv(walk.contact_step_times)
    q["step_time_cv"] = round(cv, 3) if math.isfinite(cv) else None
    r = quality.name_the_cause(
        quality.enough_walking(walk.step_count, steady_frames / clip.fps), w.dropped
    ) or quality.regular_steps(walk.contact_step_times)
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
        # Label-free knee/hip measures (Phase 11). Not for the treadmill: the belt carries the standing
        # foot back, so a footprint doesn't stay put.
        kinematics=measure_kinematics(clip, segments, tracks),
    )


def _analyse_treadmill(
    clip: Clip, _calibration: Calibration | None, q: dict[str, object], belt_speed_m_s: float | None
) -> AnalysisResult:
    """Walking on a treadmill filmed side-on (Plan V3 Phase 9). The walker stays in place, so the
    stretches where the pelvis doesn't travel are measured (segments.in_place_segments), with the same
    event detection, side-view, step-count and regularity checks as the walk. There is no path across
    the floor to check, and no floor calibration: the belt moves under the feet. Step length comes
    from the entered belt speed instead. Not yet validated: no treadmill reference clips yet."""
    assert belt_speed_m_s is not None
    q["feet_visible_fraction"] = round(quality.feet_fraction(clip), 3)
    q["belt_speed_m_s"] = round(belt_speed_m_s, 2)
    tracks = build_tracks(clip)
    leg_px = leg_length(tracks)
    dropped = quality.dropped_stretches(clip)
    q["second_person_s"] = round(dropped.second_person_s, 2)
    q["heels_hidden_s"] = round(dropped.heels_hidden_s, 2)
    if not math.isfinite(leg_px):
        segments: list[Segment] = []
        moving_s = 0.0
    else:
        segments = in_place_segments(clip, tracks, leg_px, facing(tracks), dropped.usable)
        moving_s = travelling_s(clip, tracks, leg_px)
    ratio = quality.view_ratio(clip, tracks, segments)
    q["view_ratio"] = round(ratio, 3) if math.isfinite(ratio) else None
    still_frames = sum(s.end - s.start for s in segments)
    q["in_place_s"] = round(still_frames / clip.fps, 2)
    q["travelling_s"] = round(moving_s, 2)
    q["usable_frame_fraction"] = round(still_frames / clip.n_frames, 3)
    r = quality.side_view(ratio) or quality.in_place(still_frames / clip.fps, moving_s)
    if r:
        return _rejected(r, q)
    walk = measure_walk(clip, segments, None, tracks=tracks)
    q["steps_detected"] = walk.step_count
    q["strides"] = {"left": len(walk.stride_times["L"]), "right": len(walk.stride_times["R"])}
    cv = quality.step_time_cv(walk.contact_step_times)
    q["step_time_cv"] = round(cv, 3) if math.isfinite(cv) else None
    r = quality.name_the_cause(
        quality.enough_walking(walk.step_count, still_frames / clip.fps), dropped
    ) or quality.regular_steps(walk.contact_step_times)
    if r:
        return _rejected(r, q)
    return AnalysisResult(
        status="accepted",
        metrics=metrics_from_treadmill(walk, belt_speed_m_s),
        quality=q,
        notes=[*notes_from_walk(walk), TREADMILL_NOTE],
        curves=curves_from_walk(walk),
    )


TREADMILL_NOTE = (
    "Measured on a treadmill. Treadmill walking isn't validated yet, and it differs from walking over "
    "the ground, so compare it only with your other treadmill tests."
)

# A test type is added here with its own checks. The walk is validated on LJMU (Plan V3 Phase 3);
# the treadmill isn't yet, and every value it gives says so (accuracy.TREADMILL_UNVALIDATED).
TESTS: dict[str, Callable[[Clip, Calibration | None, dict[str, object], float | None], AnalysisResult]] = {
    WALK: _analyse_walk,
    TREADMILL: _analyse_treadmill,
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


def analyse_video(
    path: str, calibration: Calibration | None = None, test: str = WALK, belt_speed_m_s: float | None = None
) -> AnalysisResult:
    from gaitcore.landmarks import extract_clip

    if test not in TESTS:
        raise UnsupportedTest(test)
    info = probe(path)
    early = precheck(info, test)
    if early:
        return early
    if calibration is not None:
        calibration.check(info.width, info.height)
    return analyse(extract_clip(path), calibration, test, belt_speed_m_s)
