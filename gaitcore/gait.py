"""Gait events and per-step / per-stride measurements (ADR-006 steps 6-7; audit F24, F27).

Heel strike: the frame where the heel is furthest ahead of the pelvis in the walking direction
(Zeni JA, Richards JG, Higginson JS. Two simple methods for determining gait events during treadmill
and overground walking using kinematic data. Gait Posture 2008;27(4):710-714), applied to the 2D
side view with the pelvis = midpoint of the hips. Both legs are detected, so cadence counts every
step.

Peak detection thresholds:
- MIN_STRIDE_S = 0.5 s between strikes of the same foot (240 steps/min): faster than any walking
  cadence, so it only removes jitter peaks. Physical bound.
- PROMINENCE = 0.1 leg lengths: the heel travels roughly 0.6-1.0 leg lengths relative to the pelvis
  in each stride; a peak must rise at least 0.1 above its surroundings. Checked against 6 deg knee
  jitter on synthetic ground truth (_audit/tests, tests/test_measurement.py).
A step is counted only between strikes of alternate feet, STEP_S_RANGE apart; a stride only when
exactly one strike of the other foot lies between two strikes of the same foot, so a missed event
never produces a double-length step or stride.

Per stride, a leg's knee and thigh angles are used only if every frame of the stride is valid for
that leg (no masked landmark): a peak inside a gap could otherwise be missed.

Step length (calibrated only): distance along the calibration axis between the two heels' floor
positions. A heel's floor position for a strike is its median position from that strike to the
next strike of the other foot, when the foot is on the floor, which makes it insensitive to the
exact heel-strike frame.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.signal import find_peaks

from gaitcore.angles import knee_flexion, thigh_angle
from gaitcore.calibration import Calibration
from gaitcore.clip import Clip
from gaitcore.segments import Segment
from gaitcore.signals import Tracks, build_tracks, runs

MIN_STRIDE_S = 0.5
PROMINENCE = 0.1
STEP_S_RANGE = (0.25, 2.0)
STRIDE_S_RANGE = (0.5, 4.0)


def leg_length(tracks: Tracks) -> float:
    """Median thigh + shank length in pixels over frames where a whole leg is visible."""
    lengths = []
    for side in ("L", "R"):
        thigh = np.linalg.norm(tracks[(side, "knee")] - tracks[(side, "hip")], axis=1)
        shank = np.linalg.norm(tracks[(side, "ankle")] - tracks[(side, "knee")], axis=1)
        lengths.append(thigh + shank)
    all_l = np.concatenate(lengths)
    all_l = all_l[np.isfinite(all_l)]
    return float(np.median(all_l)) if len(all_l) else math.nan


def facing(tracks: Tracks) -> float:
    """+1 if the toes point to image +x (median over both feet), else -1."""
    d = np.concatenate([tracks[(s, "toe")][:, 0] - tracks[(s, "heel")][:, 0] for s in ("L", "R")])
    d = d[np.isfinite(d)]
    return 1.0 if len(d) == 0 or np.median(d) >= 0 else -1.0


def heel_strikes(tracks: Tracks, side: str, seg: Segment, leg_px: float) -> npt.NDArray[np.int_]:
    rel = seg.direction * (tracks[(side, "heel")][:, 0] - tracks.pelvis[:, 0]) / leg_px
    window = np.full_like(rel, np.nan)
    window[seg.start : seg.end] = rel[seg.start : seg.end]
    found: list[int] = []
    for a, b in runs(np.isfinite(window)):
        peaks, _ = find_peaks(
            window[a:b], distance=max(1, math.ceil(MIN_STRIDE_S * tracks.fps)), prominence=PROMINENCE
        )
        found.extend(int(a + p) for p in peaks)
    return np.array(found, dtype=int)


@dataclass
class Walk:
    fps: float
    heel_strikes: dict[str, list[int]] = field(default_factory=lambda: {"L": [], "R": []})
    step_times: list[float] = field(default_factory=list)
    stride_times: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})
    knee_peak_flexion: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})
    hip_excursion: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})
    step_lengths_m: list[float] | None = None
    step_length_times: list[float] = field(default_factory=list)  # step times of the measured lengths

    @property
    def cadence(self) -> float:
        """Steps per minute over all valid steps."""
        return 60.0 / float(np.mean(self.step_times)) if self.step_times else math.nan

    @property
    def speed_m_s(self) -> float | None:
        if not self.step_lengths_m:
            return None
        return float(np.sum(self.step_lengths_m) / np.sum(self.step_length_times))


def _floor_position(tracks: Tracks, side: str, start: int, end: int, cal: Calibration) -> float | None:
    heel = tracks[(side, "heel")][start:end]
    heel = heel[np.isfinite(heel).all(axis=1)]
    if len(heel) < 3:
        return None
    ux, uy = cal.axis
    return float(np.median(heel[:, 0] * ux + heel[:, 1] * uy))


def measure_walk(
    clip: Clip,
    segments: list[Segment] | None = None,
    calibration: Calibration | None = None,
    tracks: Tracks | None = None,
) -> Walk:
    """Events and per-step/per-stride values. Without `segments` the whole clip is one segment
    walking the way the feet point (e.g. a treadmill-like synthetic walker)."""
    tracks = tracks or build_tracks(clip)
    leg_px = leg_length(tracks)
    walk = Walk(fps=clip.fps, step_lengths_m=[] if calibration else None)
    if not math.isfinite(leg_px) or leg_px <= 0:
        return walk
    if segments is None:
        segments = [Segment(0, clip.n_frames, facing(tracks))]
    fps = clip.fps
    for seg in segments:
        events = sorted(
            [(int(f), side) for side in ("L", "R") for f in heel_strikes(tracks, side, seg, leg_px)]
        )
        for f, side in events:
            walk.heel_strikes[side].append(f)
        # Steps: consecutive strikes of alternate feet.
        for k in range(1, len(events)):
            (f0, s0), (f1, s1) = events[k - 1], events[k]
            dt = (f1 - f0) / fps
            if s0 == s1 or not (STEP_S_RANGE[0] <= dt <= STEP_S_RANGE[1]):
                continue
            walk.step_times.append(dt)
            if calibration is not None and walk.step_lengths_m is not None:
                nxt = events[k + 1][0] if k + 1 < len(events) else min(seg.end, f1 + (f1 - f0))
                p_new = _floor_position(tracks, s1, f1, nxt, calibration)
                p_old = _floor_position(tracks, s0, f0, f1, calibration)
                if p_new is not None and p_old is not None:
                    walk.step_lengths_m.append(abs(p_new - p_old) * calibration.metres_per_pixel)
                    walk.step_length_times.append(dt)
        # Strides: same foot, exactly one strike of the other foot in between.
        for k in range(2, len(events)):
            (f0, s0), (_, sm), (f1, s1) = events[k - 2], events[k - 1], events[k]
            dt = (f1 - f0) / fps
            if not (s0 == s1 != sm and STRIDE_S_RANGE[0] <= dt <= STRIDE_S_RANGE[1]):
                continue
            walk.stride_times[s0].append(dt)
            sl = slice(f0, f1 + 1)
            hip, knee, ankle = (tracks[(s0, n)][sl] for n in ("hip", "knee", "ankle"))
            if np.isfinite(np.c_[hip, knee, ankle]).all():
                walk.knee_peak_flexion[s0].append(
                    float(np.max(knee_flexion(hip, knee, ankle, seg.direction)))
                )
                th = thigh_angle(hip, knee, seg.direction)
                walk.hip_excursion[s0].append(float(np.max(th) - np.min(th)))
    return walk
