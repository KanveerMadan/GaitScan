"""Input quality gate (ADR-005/006; audit F26, F29). A clip that fails gets no numbers, only a
specific reason the user can act on. Checks run in this order; the first failure is reported.

| Code | Rule | Basis |
|---|---|---|
| too_short | duration < MIN_DURATION_S (3 s) | Physical: MIN_STEPS steps at a brisk 130 steps/min (CADENCE-Adults' vigorous threshold, Tudor-Locke 2019) take 2.8 s. |
| low_frame_rate | fps < MIN_FPS (24) | Literature: Stenum et al. 2021 obtained ~20 ms temporal accuracy from 25 Hz video; 24 fps (41.7 ms/frame) is the common rate just below. |
| no_person | a pose in < MIN_POSE_FRAMES frames | Nothing to measure. |
| multiple_people | > MAX_MULTI_FRACTION (10%) of frames with a pose have 2+ people | Frames with 2+ people are always masked (we can't tell who is who); above 10% the walk is too fragmented. Design threshold. |
| wrong_orientation | median trunk angle from vertical > MAX_TRUNK_TILT (45 deg) | Physical: an upright walker's trunk leans well under 45 deg; above it the video is rotated or the person is not upright. |
| feet_not_visible | both heels and both ankles visible in < MIN_FEET_FRACTION (50%) of the frames where the hips are in view | Heel strikes need both heels. Counted only while the person is in the picture, so walking out of frame is not mistaken for hidden feet. Design threshold. |
| not_side_view | median shoulder width / trunk length > MAX_VIEW_RATIO (0.35) | Geometry: biacromial breadth / trunk length is ~0.90 in Winter's segment proportions (2009); MediaPipe's shoulder points sit inside the acromia, so ~0.8 is ASSUMED for the frontal ratio (to be checked on the Phase 3 multi-view data). At camera yaw a the ratio is ~0.8 sin a, so 0.35 = ~26 deg, about where a 60 deg knee flexion reads 5 deg low in the audit's projection probe (out_view_dependency.txt: 58.4 deg at 15 deg yaw, 53.5 deg at 30 deg). |
| too_little_walking | fewer than MIN_STEPS (6) steps in steady passes | Measurement resolution: event timing is quantised to 1 frame; over 6 steps at 30 fps that bounds cadence error to about 1 step/min. |
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from gaitcore.angles import segment_angle
from gaitcore.clip import Clip
from gaitcore.segments import Segment
from gaitcore.signals import SIDES, Tracks, masked_xy, raw_xy, single_person

MIN_DURATION_S = 3.0
MIN_FPS = 24.0
MIN_POSE_FRAMES = 10
MAX_MULTI_FRACTION = 0.10
MAX_TRUNK_TILT = 45.0
MIN_FEET_FRACTION = 0.5
MAX_VIEW_RATIO = 0.35
MIN_STEPS = 6

CAPTURE_TIP = (
    "Film from the side with the phone held still at hip height, 3-4 m from the walking line, "
    "with the whole body in view, and walk across the frame and back at your usual pace."
)


@dataclass(frozen=True)
class Rejection:
    code: str
    message: str


def too_short(duration_s: float) -> Rejection | None:
    if duration_s < MIN_DURATION_S:
        return Rejection(
            "too_short",
            f"The video is {duration_s:.1f} s long. Record at least {MIN_DURATION_S:.0f} s of walking; "
            f"10-20 s works best. {CAPTURE_TIP}",
        )
    return None


def low_frame_rate(fps: float) -> Rejection | None:
    if fps < MIN_FPS:
        return Rejection(
            "low_frame_rate",
            f"The video was recorded at {fps:.0f} frames per second. Record at 30 frames per second or more "
            f"(at least {MIN_FPS:.0f}).",
        )
    return None


def has_pose(clip: Clip) -> npt.NDArray[np.bool_]:
    return np.asarray(np.isfinite(clip.landmarks["lm23_x"].to_numpy(dtype=float)))


def people(clip: Clip) -> Rejection | None:
    pose = has_pose(clip)
    if pose.sum() < MIN_POSE_FRAMES:
        return Rejection("no_person", f"No person was detected in the video. {CAPTURE_TIP}")
    multi = float((~single_person(clip) & pose).sum() / pose.sum())
    if multi > MAX_MULTI_FRACTION:
        return Rejection(
            "multiple_people",
            f"More than one person was detected in {multi:.0%} of the video. "
            "Record with only the person who is walking in view.",
        )
    return None


def _mid(clip: Clip, a: int, b: int) -> npt.NDArray[np.float64]:
    return np.asarray((raw_xy(clip, a) + raw_xy(clip, b)) / 2)


def trunk_tilt(clip: Clip) -> float:
    """Median angle of the shoulder-midpoint -> hip-midpoint line from the downward vertical."""
    ang = np.abs(segment_angle(_mid(clip, 11, 12), _mid(clip, 23, 24), 1.0))
    ang = ang[np.isfinite(ang)]
    return float(np.median(ang)) if len(ang) else math.nan


def orientation(clip: Clip) -> Rejection | None:
    tilt = trunk_tilt(clip)
    if math.isfinite(tilt) and tilt > MAX_TRUNK_TILT:
        return Rejection(
            "wrong_orientation",
            "The person appears sideways or upside down in the video. Hold the phone so the person is "
            "upright on screen, and check that the video isn't rotated.",
        )
    return None


def feet_fraction(clip: Clip) -> float:
    """Share of the frames with both hips in view in which both heels and both ankles are visible."""
    pose = np.isfinite(masked_xy(clip, 23)).all(axis=1) & np.isfinite(masked_xy(clip, 24)).all(axis=1)
    ok = np.ones(clip.n_frames, dtype=bool)
    for idx in SIDES.values():
        for name in ("ankle", "heel"):
            ok &= np.isfinite(masked_xy(clip, idx[name])).all(axis=1)
    return float((ok & pose).sum() / max(pose.sum(), 1))


def feet(clip: Clip) -> Rejection | None:
    frac = feet_fraction(clip)
    if frac < MIN_FEET_FRACTION:
        return Rejection(
            "feet_not_visible",
            f"Both feet were clearly visible in only {frac:.0%} of the time the person was in view. Keep the whole body, "
            "including both feet, in the frame, with nothing in front of the legs.",
        )
    return None


def view_ratio(clip: Clip, tracks: Tracks, segments: list[Segment]) -> float:
    """Median shoulder width / trunk length: ~0 side-on, ~0.8 facing the camera. Measured over the
    walking passes, or over every frame if there are none."""
    frames = np.zeros(clip.n_frames, dtype=bool)
    for s in segments:
        frames[s.start : s.end] = True
    if not frames.any():
        frames[:] = True
    sl, sr = tracks[("L", "shoulder")], tracks[("R", "shoulder")]
    trunk = np.linalg.norm((sl + sr) / 2 - tracks.pelvis, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.abs(sl[:, 0] - sr[:, 0]) / trunk
    r = r[frames & np.isfinite(r)]
    return float(np.median(r)) if len(r) else math.nan


def side_view(ratio: float) -> Rejection | None:
    if math.isfinite(ratio) and ratio > MAX_VIEW_RATIO:
        return Rejection(
            "not_side_view",
            "The camera doesn't seem to be at the side of the walking path. Place the phone side-on, "
            "at right angles to the direction of walking.",
        )
    return None


def enough_walking(n_steps: int) -> Rejection | None:
    if n_steps < MIN_STEPS:
        return Rejection(
            "too_little_walking",
            f"Only {n_steps} steps of steady walking could be measured; at least {MIN_STEPS} are needed. "
            f"{CAPTURE_TIP}",
        )
    return None
