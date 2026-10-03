"""Steady-state walking passes (ADR-006 step 5).

A frame belongs to a pass when:
- the whole lower body (hips, knees, ankles, heels of both legs) is inside the image (out-of-frame
  spans are excluded; MediaPipe extrapolates landmarks beyond the border, so their raw coordinates
  are checked, not their visibility);
- the pelvis moves horizontally at >= V_MIN leg lengths per second (standing, turning and walking
  towards/away from the camera are excluded), always in the same direction (turns split passes);
- its speed, averaged over SMOOTH_S, is within +-STEADY_BAND of the pass's median speed, which
  removes acceleration at the start and deceleration at the end of a pass.

Thresholds:
- V_MIN = 0.25 leg lengths/s: ~0.2 m/s for a 0.85 m leg, below the slowest walking speeds people
  use; anything slower is treated as standing or turning. Physical bound.
- SMOOTH_S = 1.0 s: about one stride, so the within-stride surge of the pelvis averages out.
- STEADY_BAND = 0.20: design threshold, checked on synthetic ground truth (tests/test_measurement.py):
  it keeps the constant-speed part of a pass and drops the ramps.
- MIN_SEGMENT_S = 1.0 s: shorter than one stride cannot contain a measurable stride.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from gaitcore.clip import Clip
from gaitcore.signals import LOWER_LIMB, SIDES, Tracks, raw_xy, runs

V_MIN = 0.25
SMOOTH_S = 1.0
STEADY_BAND = 0.20
MIN_SEGMENT_S = 1.0


@dataclass(frozen=True)
class Segment:
    start: int  # first frame
    end: int  # one past the last frame
    direction: float  # +1: walking towards image +x; -1: towards -x

    def seconds(self, fps: float) -> float:
        return (self.end - self.start) / fps


def body_in_frame(clip: Clip) -> npt.NDArray[np.bool_]:
    ok = np.ones(clip.n_frames, dtype=bool)
    for idx in SIDES.values():
        for name in LOWER_LIMB:
            xy = raw_xy(clip, idx[name])
            with np.errstate(invalid="ignore"):
                ok &= (xy[:, 0] >= 0) & (xy[:, 0] <= clip.width) & (xy[:, 1] >= 0) & (xy[:, 1] <= clip.height)
    return ok


def pelvis_speed(tracks: Tracks, leg_px: float) -> npt.NDArray[np.float64]:
    """Signed horizontal pelvis speed in leg lengths per second, averaged over SMOOTH_S."""
    x = tracks.pelvis[:, 0]
    v = np.full_like(x, np.nan)
    v[1:-1] = (x[2:] - x[:-2]) / 2 * tracks.fps / leg_px
    win = max(3, int(round(SMOOTH_S * tracks.fps)) | 1)
    return np.asarray(pd.Series(v).rolling(win, center=True, min_periods=win).mean().to_numpy(), dtype=float)


def steady_segments(clip: Clip, tracks: Tracks, leg_px: float) -> list[Segment]:
    v = pelvis_speed(tracks, leg_px)
    with np.errstate(invalid="ignore"):
        moving = body_in_frame(clip) & (np.abs(v) >= V_MIN)
    out: list[Segment] = []
    for sign in (1.0, -1.0):
        with np.errstate(invalid="ignore"):
            same = moving & (np.sign(v) == sign)
        for s, e in runs(same):
            speed = np.abs(v[s:e])
            med = float(np.median(speed))
            steady = (speed >= (1 - STEADY_BAND) * med) & (speed <= (1 + STEADY_BAND) * med)
            for a, b in runs(steady):
                if b - a >= MIN_SEGMENT_S * tracks.fps:
                    out.append(Segment(s + a, s + b, sign))
    return sorted(out, key=lambda g: g.start)
