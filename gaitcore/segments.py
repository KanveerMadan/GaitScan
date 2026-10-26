"""Steady-state walking passes (ADR-006 step 5).

A frame belongs to a pass when:
- the pelvis is in view (both hips visible and inside the image). Out-of-frame data is excluded
  per landmark rather than per frame: every landmark outside the image is masked (signals.py), a
  heel strike needs that heel and the pelvis, and a stride's knee/hip values need every frame of the
  stride. So a strike of the leading foot still counts while the trailing foot is outside the frame,
  which is what happens at the edges of a narrow (e.g. portrait) frame;
- the pelvis moves horizontally at >= V_MIN leg lengths per second (standing, turning and walking
  towards/away from the camera are excluded), always in the same direction (turns split passes);
- its speed, averaged over SMOOTH_S, is within +-STEADY_BAND of the pass's median speed, which
  removes acceleration at the start and deceleration at the end of a pass.

Thresholds:
- V_MIN = 0.25 leg lengths/s: ~0.2 m/s for a 0.85 m leg, below the slowest walking speeds people
  use; anything slower is treated as standing or turning. Physical bound.
- SMOOTH_S = 0.5 s: about one step period (0.46-0.67 s at 90-130 steps/min). The pelvis speeds up
  and slows down once per step, so averaging over one step removes that surge; the residual ripple
  at slower cadences stays well inside STEADY_BAND.
- STEADY_BAND = 0.20: design threshold, checked on synthetic ground truth (tests/test_measurement.py):
  it keeps the constant-speed part of a pass and drops the ramps.
- MIN_SEGMENT_S = 0.46 s: one step at 130 steps/min; a shorter span cannot hold the two heel
  strikes a step needs. (Short passes are normal when a narrow frame is crossed in ~1 s; steps from
  several passes are pooled.)
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from gaitcore.clip import Clip
from gaitcore.signals import Tracks, masked_xy, runs

V_MIN = 0.25
SMOOTH_S = 0.5
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
        k = len({g.pass_index for g in out})
        out.extend(
            Segment(s + a, s + b, sign, k) for a, b in runs(steady) if b - a >= MIN_SEGMENT_S * tracks.fps
        )
    return out
