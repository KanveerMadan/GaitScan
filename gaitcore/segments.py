"""Steady-state walking passes (ADR-006 step 5).

A frame belongs to a pass when:
- the pelvis is in view (both hips visible and inside the image). Out-of-frame data is excluded
  per landmark rather than per frame: every landmark outside the image is masked (signals.py), a
  heel strike needs that heel and the pelvis, and a stride's knee/hip values need every frame of the
  stride. So a strike of the leading foot still counts while the trailing foot is outside the frame,
  which is what happens at the edges of a narrow (e.g. portrait) frame;
- the pelvis moves horizontally at >= V_MIN leg lengths per second (standing, turning and walking
  towards/away from the camera are excluded), always in the same direction (turns split passes);
- its speed, averaged over one of the walker's own steps, is within +-STEADY_BAND of the pass's
  median speed, which removes acceleration at the start and deceleration at the end of a pass;
- it isn't in a stretch the measurement can't use (quality.dropped_stretches: a second person in
  view, or neither heel visible, for at least one step). The rest of the pass still counts.

Thresholds:
- V_MIN = 0.25 leg lengths/s: ~0.2 m/s for a 0.85 m leg, below the slowest walking speeds people
  use; anything slower is treated as standing or turning. Physical bound.
- Averaging window = the walker's own median step time (gait.typical_step_s), kept within
  SMOOTH_RANGE_S (0.5-1.0 s: one step at 120-60 steps/min); SMOOTH_S (0.5 s) when fewer than 4 steps
  are found. The pelvis speeds up and slows down once per step, and averaging over exactly one step
  removes that surge. A fixed 0.5 s left too much of it in at slow cadences: on phone clips the hip
  midpoint ripples by ~20% of the speed per step and ~8% per stride, and at ~85 steps/min (0.7 s
  steps) every pass broke into pieces too short to hold a step (2 of 3 real clips undercounted, 1
  rejected; the synthetic walker in tests/test_measurement.py reproduces it). Checked on LJMU (Topham
  et al. 2023, CC BY 4.0), together with the dropped stretches: evaluation/results.
- STEADY_BAND = 0.20: design threshold, checked on synthetic ground truth (tests/test_measurement.py):
  it keeps the constant-speed part of a pass and drops the ramps.
- MIN_SEGMENT_S = 0.46 s: one step at 130 steps/min; a shorter span cannot hold the two heel
  strikes a step needs. (Short passes are normal when a narrow frame is crossed in ~1 s; steps from
  several passes are pooled.)

On a treadmill (in_place_segments) the walker never crosses the frame. There a frame counts when the
pelvis is in view and moves at < V_MIN (the same bound: slower than anyone walks, so not travelling),
outside the dropped stretches, in runs of at least MIN_SEGMENT_S. No new threshold: whether the legs
are actually walking is left to the step count and step regularity checks every walk passes.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from gaitcore.clip import Clip
from gaitcore.signals import Tracks, masked_xy, runs

V_MIN = 0.25
SMOOTH_S = 0.5
SMOOTH_RANGE_S = (0.5, 1.0)
STEADY_BAND = 0.20
MIN_SEGMENT_S = 60 / 130


@dataclass(frozen=True)
class Segment:
    start: int  # first frame
    end: int  # one past the last frame
    direction: float  # +1: walking towards image +x; -1: towards -x
    pass_index: int = 0  # which walk across the frame; a pass can hold several steady segments

    def seconds(self, fps: float) -> float:
        return (self.end - self.start) / fps


def pelvis_in_view(clip: Clip) -> npt.NDArray[np.bool_]:
    return np.asarray(
        np.isfinite(masked_xy(clip, 23)).all(axis=1) & np.isfinite(masked_xy(clip, 24)).all(axis=1)
    )


def pelvis_speed(tracks: Tracks, leg_px: float, smooth_s: float = SMOOTH_S) -> npt.NDArray[np.float64]:
    """Signed horizontal pelvis speed in leg lengths per second, averaged over smooth_s."""
    x = tracks.pelvis[:, 0]
    v = np.full_like(x, np.nan)
    v[1:-1] = (x[2:] - x[:-2]) / 2 * tracks.fps / leg_px
    win = max(3, int(round(smooth_s * tracks.fps)) | 1)
    return np.asarray(pd.Series(v).rolling(win, center=True, min_periods=win).mean().to_numpy(), dtype=float)


def steady_segments(
    clip: Clip,
    tracks: Tracks,
    leg_px: float,
    smooth_s: float = SMOOTH_S,
    usable: npt.NDArray[np.bool_] | None = None,
) -> list[Segment]:
    """Steady walking, with speeds averaged over smooth_s; only frames in `usable`, if given."""
    v = pelvis_speed(tracks, leg_px, smooth_s)
    with np.errstate(invalid="ignore"):
        moving = pelvis_in_view(clip) & (np.abs(v) >= V_MIN)
    crossings: list[tuple[int, int, float]] = []  # one per walk across: moving one way, unbroken
    for sign in (1.0, -1.0):
        with np.errstate(invalid="ignore"):
            same = moving & (np.sign(v) == sign)
        crossings.extend((s, e, sign) for s, e in runs(same))
    out: list[Segment] = []
    for s, e, sign in sorted(crossings):
        speed = np.abs(v[s:e])
        med = float(np.median(speed))
        steady = (speed >= (1 - STEADY_BAND) * med) & (speed <= (1 + STEADY_BAND) * med)
        if usable is not None:
            steady &= usable[s:e]
        k = len({g.pass_index for g in out})
        out.extend(
            Segment(s + a, s + b, sign, k) for a, b in runs(steady) if b - a >= MIN_SEGMENT_S * tracks.fps
        )
    return out


def in_place_segments(
    clip: Clip,
    tracks: Tracks,
    leg_px: float,
    direction: float,
    usable: npt.NDArray[np.bool_] | None = None,
) -> list[Segment]:
    """Walking in place, as on a treadmill: the pelvis in view and not travelling (module docstring).
    `direction` is the way the walker faces (gait.facing); every segment is pass 0."""
    v = pelvis_speed(tracks, leg_px)
    with np.errstate(invalid="ignore"):
        still = pelvis_in_view(clip) & (np.abs(v) < V_MIN)
    if usable is not None:
        still &= usable
    return [Segment(a, b, direction, 0) for a, b in runs(still) if b - a >= MIN_SEGMENT_S * tracks.fps]


def travelling_s(clip: Clip, tracks: Tracks, leg_px: float) -> float:
    """Seconds in which the pelvis is in view and moving across the frame at >= V_MIN."""
    with np.errstate(invalid="ignore"):
        moving = pelvis_in_view(clip) & (np.abs(pelvis_speed(tracks, leg_px)) >= V_MIN)
    return float(moving.sum()) / tracks.fps
