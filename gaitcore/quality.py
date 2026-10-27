"""Input quality gate (ADR-005/006; audit F26, F29). A clip that fails gets no numbers, only a
specific reason the user can act on. Checks run in this order; the first failure is reported
(multiple_people and feet_not_visible replace view_unconfirmed / too_little_walking: see their rows).

| Code | Rule | Basis |
|---|---|---|
| too_short | duration < MIN_DURATION_S (3 s) | Physical: MIN_STEPS steps at a brisk 130 steps/min (CADENCE-Adults' vigorous threshold, Tudor-Locke 2019) take 2.8 s. |
| low_frame_rate | fps < MIN_FPS (24) | Literature: Stenum et al. 2021 obtained ~20 ms temporal accuracy from 25 Hz video; 24 fps (41.7 ms/frame) is the common rate just below. |
| no_person | a pose in < MIN_POSE_FRAMES frames | Nothing to measure. |
| multiple_people | too little steady walking is left (view_unconfirmed or too_little_walking below), at least one step's worth of frames (MIN_SEGMENT_S) had a second person in view, and more than had hidden heels | Frames with 2+ people are always masked (we can't tell who is who), whether in a long stretch or a few frames at a time. Stretches of at least one step are dropped from steady walking and the rest is measured if it passes every later check, instead of rejecting the whole video. The message names this cause only when too little walking is left. |
| wrong_orientation | median trunk angle from vertical > MAX_TRUNK_TILT (45 deg) | Physical: an upright walker's trunk leans well under 45 deg; above it the video is rotated or the person is not upright. |
| feet_not_visible | as multiple_people, for stretches of at least one step in which neither heel is visible while the hips are in view (hidden, or outside the frame) | Step events need the heels. A brief loss (shorter than a step) is kept: the heel-separation signal bridges it. Walking out of frame is not counted as hidden feet. |
| not_side_view | median shoulder width / trunk length > MAX_VIEW_RATIO (0.35) | Geometry: biacromial breadth / trunk length is ~0.90 in Winter's segment proportions (2009); MediaPipe's shoulder points sit inside the acromia, so ~0.8 is ASSUMED for the frontal ratio (to be checked on the Phase 3 multi-view data). At camera yaw a the ratio is ~0.8 sin a, so 0.35 = ~26 deg, about where a 60 deg knee flexion reads 5 deg low in the audit's projection probe (out_view_dependency.txt: 58.4 deg at 15 deg yaw, 53.5 deg at 30 deg). |
| not_side_view | angle between the ankle path and the shoulder path while walking across the frame > MAX_PATH_CONVERGENCE (4.8 deg) | Data: side-on, both paths run parallel to the floor; a walk that also moves towards or away from the camera makes them converge in perspective. LJMU (Topham et al. 2023, CC BY 4.0), 24 participants, 45 vs 90 deg cameras, leave-one-participant-out: threshold 4.83 deg, accuracy 0.986, 1/70 45 deg clips accepted, 1/69 90 deg clips rejected (the shoulder-width rule alone accepted 29/70). An angle between two image lines, so a rolled phone doesn't change it (+-5 deg roll simulated on LJMU: 0-4% of 90 deg clips rejected). On the synthetic pinhole walker 3.5 m away it trips at ~16 deg yaw. |
| view_unconfirmed | the path angle can't be measured: fewer than MIN_SEGMENT_S (one step) of frames walking across the frame | Without it the side-on view isn't confirmed, so no numbers. |
| legs_not_tracked | fewer than MIN_STEPS steps although the steady passes last >= MIN_STEADY_FOR_STEPS_S (4 s) | Physical: 4 s of steady walking holds 6 steps even at 90 steps/min (0.67 s per step), the slow end of normal adult walking, so finding fewer means the legs weren't followed, not that the walk was too short. The user is told to fix the lighting / clothing / view, not to walk longer. Checked on LJMU (Topham et al. 2023, CC BY 4.0), 192 side-view clips: it fired on 20, and in all 20 an independent pose model (RTMPose footprint strikes) found 7-13 steps in the steady walking. |
| too_little_walking | fewer than MIN_STEPS (6) steps in steady passes | Measurement resolution: event timing is quantised to 1 frame; over 6 steps at 30 fps that bounds cadence error to about 1 step/min. |
| irregular_steps | label-free step times (gait.py) have SD / mean > MAX_STEP_TIME_CV (0.15) | Data: spurious heel-separation peaks between real steps make the step times irregular and the cadence wrong. LJMU held-out set (Topham et al. 2023, CC BY 4.0; 60 accepted clips, 34 participants not in the 28-clip ground-truth set; reference RTMPose footprint strikes, large disagreements settled visually): every cadence error over 6 steps/min had CV > 0.15; at 0.15, 54 clips kept, MAE 2.66 -> 1.70, max 24.4 -> 5.4 steps/min, 2 correct clips lost. Chosen on that set, not on phone clips. |

Dropping stretches instead of rejecting the video (multiple_people, feet_not_visible): on three
phone clips, a second person crossing for a few seconds, or the feet leaving the bottom of the
frame, rejected or shortened walks whose other passes were clean. Before, more than 10% of frames
with two people, or both feet visible in under 50% of the frames, rejected the whole video. The
remaining walking still has to pass the unchanged step-count, regularity and side-view checks.
Checked on LJMU (Topham et al. 2023, CC BY 4.0) and the three phone clips, together with the
steadiness window (segments.py): evaluation/results.
"""

import math
import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from gaitcore.angles import segment_angle
from gaitcore.clip import Clip
from gaitcore.segments import MIN_SEGMENT_S, V_MIN, Segment, pelvis_in_view, pelvis_speed
from gaitcore.signals import SIDES, Tracks, masked_xy, raw_xy, runs, single_person

MIN_DURATION_S = 3.0
MIN_FPS = 24.0
MIN_POSE_FRAMES = 10
MAX_TRUNK_TILT = 45.0
MAX_VIEW_RATIO = 0.35
MAX_PATH_CONVERGENCE = 4.8
MIN_STEPS = 6
MIN_STEADY_FOR_STEPS_S = 4.0
# Chosen on the held-out LJMU set (2026-10-24, table above). Re-validate on real phone clips in
# Phase 3. A genuinely uneven gait also has a high CV (alternating 0.5 / 0.7 s steps give 0.18), so
# a limp may be rejected as irregular; also a Phase 3 check.
MAX_STEP_TIME_CV = 0.15

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
    """No person at all. A second person only removes the stretches they are in (dropped_stretches)."""
    if has_pose(clip).sum() < MIN_POSE_FRAMES:
        return Rejection("no_person", f"No person was detected in the video. {CAPTURE_TIP}")
    return None


def _mid(clip: Clip, a: int, b: int) -> npt.NDArray[np.float64]:
    return np.asarray((raw_xy(clip, a) + raw_xy(clip, b)) / 2)


def trunk_tilt(clip: Clip) -> float:
    """Median angle of the shoulder-midpoint -> hip-midpoint line from the downward vertical, over the
    frames with one person (with two, the pose may be the other person's)."""
    ang = np.abs(segment_angle(_mid(clip, 11, 12), _mid(clip, 23, 24), 1.0))
    ang = ang[np.isfinite(ang) & single_person(clip)]
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


@dataclass(frozen=True)
class Dropped:
    """Stretches of at least one step (MIN_SEGMENT_S) that steady walking leaves out: neither heel
    visible, either because a second person is in view (every landmark is then masked) or because the
    feet are hidden or outside the frame."""

    usable: npt.NDArray[np.bool_]  # per frame: False inside a dropped stretch
    second_person_s: float  # every frame with two or more people: always masked, dropped or not
    heels_hidden_s: float  # dropped frames with one person whose hips are in view


def dropped_stretches(clip: Clip) -> Dropped:
    heel = np.zeros(clip.n_frames, dtype=bool)
    for idx in SIDES.values():
        heel |= np.isfinite(masked_xy(clip, idx["heel"])).all(axis=1)
    usable = np.ones(clip.n_frames, dtype=bool)
    for a, b in runs(~heel):
        if b - a >= MIN_SEGMENT_S * clip.fps:
            usable[a:b] = False
    one = single_person(clip)
    second = has_pose(clip) & ~one
    hidden = ~usable & one & pelvis_in_view(clip)
    return Dropped(usable, float(second.sum() / clip.fps), float(hidden.sum() / clip.fps))


def name_the_cause(r: Rejection | None, dropped: Dropped) -> Rejection | None:
    """Too little walking left after dropping stretches: say what was in the way, not just 'walk more'."""
    if r is None or r.code not in ("view_unconfirmed", "too_little_walking"):
        return r
    if max(dropped.second_person_s, dropped.heels_hidden_s) < MIN_SEGMENT_S:  # less than a step lost
        return r
    if dropped.second_person_s >= dropped.heels_hidden_s:
        return Rejection(
            "multiple_people",
            f"Another person was in view for {dropped.second_person_s:.0f} s of the video. Those parts can't "
            "be measured, and what's left has too little steady walking. Record with only the person who is "
            "walking in view.",
        )
    return Rejection(
        "feet_not_visible",
        f"Neither heel could be seen for {dropped.heels_hidden_s:.0f} s while the person was in view. Those "
        "parts can't be measured, and what's left has too little steady walking. Keep the whole body, including "
        "both feet, in the frame, with nothing in front of the legs.",
    )


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


NOT_SIDE_VIEW = Rejection(
    "not_side_view",
    "The camera doesn't seem to be at the side of the walking path. Place the phone side-on, "
    "at right angles to the direction of walking.",
)


def side_view(ratio: float) -> Rejection | None:
    return NOT_SIDE_VIEW if math.isfinite(ratio) and ratio > MAX_VIEW_RATIO else None


def _line_angle(xy: npt.NDArray[np.float64], need: int) -> float:
    """Angle from horizontal (deg) of the least-squares line y(x) through the finite points."""
    ok = np.isfinite(xy).all(axis=1)
    if ok.sum() < need or np.ptp(xy[ok, 0]) == 0:
        return math.nan
    return math.degrees(math.atan(float(np.polyfit(xy[ok, 0], xy[ok, 1], 1)[0])))


def path_convergence(clip: Clip, tracks: Tracks, leg_px: float) -> float:
    """Angle (deg) between the ankle path and the shoulder-midpoint path over the frames where the
    person walks across the frame (pelvis in view, moving >= V_MIN). The ankle path is the mean of
    the visible ankles. NaN with fewer than MIN_SEGMENT_S of such frames."""
    with np.errstate(invalid="ignore"):
        walking = pelvis_in_view(clip) & (np.abs(pelvis_speed(tracks, leg_px)) >= V_MIN)
    shoulders = (masked_xy(clip, 11) + masked_xy(clip, 12)) / 2
    ankles = np.stack([masked_xy(clip, idx["ankle"]) for idx in SIDES.values()])
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # frames with neither ankle: NaN
        ankle = np.nanmean(ankles, axis=0)
    need = math.ceil(MIN_SEGMENT_S * clip.fps)
    w = walking[:, None]
    return abs(
        _line_angle(np.where(w, ankle, np.nan), need) - _line_angle(np.where(w, shoulders, np.nan), need)
    )


def path_view(convergence: float) -> Rejection | None:
    if not math.isfinite(convergence):
        return Rejection(
            "view_unconfirmed",
            f"We couldn't confirm a side-on camera view: walk straight across the frame, from one side to "
            f"the other. {CAPTURE_TIP}",
        )
    return NOT_SIDE_VIEW if convergence > MAX_PATH_CONVERGENCE else None


def enough_walking(n_steps: int, steady_s: float) -> Rejection | None:
    if n_steps >= MIN_STEPS:
        return None
    if steady_s >= MIN_STEADY_FOR_STEPS_S:
        return Rejection(
            "legs_not_tracked",
            f"The video has {steady_s:.0f} s of steady walking, but the legs couldn't be followed well enough "
            f"to count the steps (only {n_steps} found). Film in even light with the light behind the camera, "
            "not behind the person, wear clothes that stand out from the floor and background, and keep both "
            "legs in view from the hips to the heels.",
        )
    return Rejection(
        "too_little_walking",
        f"Only {n_steps} steps of steady walking could be measured; at least {MIN_STEPS} are needed. "
        f"{CAPTURE_TIP}",
    )


def step_time_cv(step_times: list[float]) -> float:
    t = np.asarray(step_times, dtype=float)
    return float(np.std(t, ddof=1) / np.mean(t)) if len(t) >= 2 else math.nan


def regular_steps(step_times: list[float]) -> Rejection | None:
    if not step_time_cv(step_times) > MAX_STEP_TIME_CV:
        return None
    return Rejection(
        "irregular_steps",
        "The steps couldn't be timed consistently. Re-record walking steadily across the frame at your "
        "usual pace, in even light with the light behind the camera, and keep both legs in view from the "
        "hips to the heels.",
    )
