"""Landmark trajectories in pixels: masking and zero-phase low-pass filtering (ADR-006, audit F26).

Masking: a landmark is used only where MediaPipe's visibility >= VIS_MIN, it lies inside the image,
and exactly one person was detected in that frame. Masked samples are NaN and are never filled
(no interpolation): any measurement that needs them is dropped instead.

Filtering: 2nd-order Butterworth low-pass at 6 Hz applied forward and backward (filtfilt), so
zero phase lag and an effective 4th order. 6 Hz is the cut-off conventionally used for walking
kinematics (Winter, Biomechanics and Motor Control of Human Movement, 4th ed., 2009). Its fit for
this pipeline is checked on synthetic ground truth in tests/test_measurement.py: a gait-like signal
(5 harmonics of a 0.92 Hz stride) is kept within 2% of its range (the 4th/5th harmonics, 3.7/4.6 Hz,
lose ~12-26% of their amplitude) and white frame noise is reduced by more than 30% RMS.
Each contiguous run of valid samples is filtered on its own; runs too short for filtfilt's edge
padding are discarded.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt

from gaitcore.clip import Clip

Array = npt.NDArray[np.float64]

VIS_MIN = 0.5  # MediaPipe visibility is a likelihood of being visible: < 0.5 = more likely not
CUTOFF_HZ = 6.0
ORDER = 2  # per pass; filtfilt doubles it

SIDES: dict[str, dict[str, int]] = {
    "L": {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27, "heel": 29, "toe": 31},
    "R": {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28, "heel": 30, "toe": 32},
}
LOWER_LIMB = ("hip", "knee", "ankle", "heel")


def runs(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """(start, end) of each run of True, end exclusive."""
    m = np.r_[False, np.asarray(mask, dtype=bool), False].astype(np.int8)
    edges = np.flatnonzero(np.diff(m))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True)]


def single_person(clip: Clip) -> npt.NDArray[np.bool_]:
    lm = clip.landmarks
    if "n_poses" not in lm:
        return np.ones(clip.n_frames, dtype=bool)
    return np.asarray(lm["n_poses"].fillna(0).to_numpy() <= 1, dtype=bool)


def raw_xy(clip: Clip, i: int) -> Array:
    """Landmark i in pixels for every frame, unmasked (NaN only where no pose was detected)."""
    lm = clip.landmarks
    x = lm[f"lm{i}_x"].to_numpy(dtype=float) * clip.width
    y = lm[f"lm{i}_y"].to_numpy(dtype=float) * clip.height
    return np.column_stack([x, y]).astype(np.float64)


def masked_xy(clip: Clip, i: int) -> Array:
    """Landmark i in pixels, NaN where it is not visible, outside the image or the frame is ambiguous."""
    xy = raw_xy(clip, i)
    vis = clip.landmarks[f"lm{i}_vis"].to_numpy(dtype=float)
    inside = (xy[:, 0] >= 0) & (xy[:, 0] <= clip.width) & (xy[:, 1] >= 0) & (xy[:, 1] <= clip.height)
    ok = (vis >= VIS_MIN) & inside & single_person(clip)
    return np.where(ok[:, None], xy, np.nan)


def min_run(fps: float) -> int:
    b, a = butter(ORDER, CUTOFF_HZ / (fps / 2))
    return 3 * max(len(a), len(b)) + 1  # filtfilt's default padding needs more samples than this


def lowpass(xy: Array, fps: float) -> Array:
    """Zero-phase low-pass of each valid run; samples of runs too short to filter become NaN."""
    out = np.full_like(xy, np.nan)
    b, a = butter(ORDER, CUTOFF_HZ / (fps / 2))
    need = min_run(fps)
    for s, e in runs(np.asarray(np.isfinite(xy).all(axis=1))):
        if e - s >= need:
            out[s:e] = filtfilt(b, a, xy[s:e], axis=0)
    return out


@dataclass
class Tracks:
    """Masked, filtered pixel trajectories of the landmarks the pipeline uses."""

    fps: float
    points: dict[tuple[str, str], Array]  # (side, name) -> (n, 2)
    pelvis: Array  # mean of the visible hips

    def __getitem__(self, key: tuple[str, str]) -> Array:
        return self.points[key]


def build_tracks(clip: Clip) -> Tracks:
    points = {
        (side, name): lowpass(masked_xy(clip, i), clip.fps)
        for side, idx in SIDES.items()
        for name, i in idx.items()
    }
    hips = np.stack([points[("L", "hip")], points[("R", "hip")]])
    with np.errstate(invalid="ignore"):
        counts = np.isfinite(hips[:, :, 0]).sum(axis=0)
        pelvis = np.where(
            counts[:, None] > 0, np.nansum(hips, axis=0) / np.maximum(counts, 1)[:, None], np.nan
        )
    return Tracks(fps=clip.fps, points=points, pelvis=pelvis)
