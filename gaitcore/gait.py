"""Gait events and per-step / per-stride measurements (ADR-006 steps 6-7; audit F24, F27).

Cadence and step time come from label-free step events, because MediaPipe swaps the left/right leg
labels for a frame or two at a time (LJMU, Topham et al. 2023, CC BY 4.0: in the clips whose cadence
read 136-158 steps/min, ~10-12% of consecutive frames). The distance between the heels along the
walking direction, |x_L - x_R|, can't change when the labels swap. It peaks once per step, in double
support, when the feet are furthest apart:
- |x_L - x_R| / leg length on frames with one person, low-pass filtered like every other signal
  (signals.py), inside the steady passes. Heel visibility is not required: when the legs cross, the
  far heel is often marked as hidden, and requiring it would split every step.
- peaks with the same PROMINENCE (0.1 leg lengths) and at least STEP_S_RANGE[0] apart, searched for
  inside each steady pass only: a peak cut by the end of a pass is lost, but one shaped by the speed
  ramp before it is not counted (searching the whole clip read 84 for the 90 steps/min synthetic
  walker). Each peak is timed at the centre of its width at half prominence (peak_widths as in scipy,
  linearly interpolated between frames), so events are found to a fraction of a frame; the arg-max
  alone is quantised to whole frames and wanders along the flat top of the double-support plateau.
- consecutive events STEP_S_RANGE apart form a run; a gap outside it (a missed or extra peak) starts
  a new run, so a missed event never gives a double-length step.
Step time = the steps of each run, with its two alternations (steps ending on one foot, then the
other) averaged so a constant timing offset on one foot cancels, pooled over the runs by step count;
for a run with an even number of steps this is exactly its duration / its step count.
On the 27 LJMU clips with AI-annotated + cross-checked heel strikes (blind visual count confirmed by
RTMPose), this cadence was reported for 23, with a mean absolute error of 2.1 steps/min (max 12.8:
one backlit clip with a spurious event); cadence from the labelled heel strikes below was reported
for 20, with 12.0 (max 57.9).

Per-foot heel strike (used for strides, knee angles and step length, which need to know the foot): the frame where the heel is furthest ahead of the pelvis in the walking direction
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

from gaitcore.angles import thigh_angle
from gaitcore.calibration import Calibration
from gaitcore.clip import Clip
from gaitcore.dsp import find_peaks, peak_half_width_edges
from gaitcore.segments import V_MIN, Segment, pelvis_in_view, pelvis_speed
from gaitcore.signals import SIDES, Tracks, build_tracks, lowpass, raw_xy, runs, single_person

MIN_STRIDE_S = 0.5
PROMINENCE = 0.1
STEP_S_RANGE = (0.25, 2.0)
STRIDE_S_RANGE = (0.5, 4.0)
CURVE_POINTS = 101  # 0-100% of the stride
MIN_TYPICAL_STEPS = 4  # a median of fewer is one stray event away from wrong


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
        peaks = find_peaks(
            window[a:b], distance=max(1, math.ceil(MIN_STRIDE_S * tracks.fps)), prominence=PROMINENCE
        )
        found.extend(int(a + p) for p in peaks)
    return np.array(found, dtype=int)


def heel_separation(clip: Clip, leg_px: float) -> npt.NDArray[np.float64]:
    """|x_L - x_R| of the heels in leg lengths, low-pass filtered; NaN on frames with no single pose."""
    xl, xr = (raw_xy(clip, SIDES[s]["heel"])[:, 0] for s in ("L", "R"))
    sep = np.where(single_person(clip), np.abs(xl - xr) / leg_px, np.nan)
    return np.asarray(lowpass(np.c_[sep, sep], clip.fps)[:, 0])


def contact_runs(sep: npt.NDArray[np.float64], seg: Segment, fps: float) -> list[list[float]]:
    """Label-free step events (s) in a steady pass, grouped into runs of consecutive steps."""
    window = np.full_like(sep, np.nan)
    window[seg.start : seg.end] = sep[seg.start : seg.end]
    out: list[list[float]] = []
    for a, b in runs(np.isfinite(window)):
        w = window[a:b]
        peaks = find_peaks(w, distance=max(1, math.ceil(STEP_S_RANGE[0] * fps)), prominence=PROMINENCE)
        if not len(peaks):
            continue
        left, right = peak_half_width_edges(w, peaks)
        run: list[float] = []
        for t in (a + (left + right) / 2) / fps:
            if run and not (STEP_S_RANGE[0] <= t - run[-1] <= STEP_S_RANGE[1]):
                out.append(run)
                run = []
            run.append(float(t))
        out.append(run)
    return [r for r in out if len(r) >= 2]


def typical_step_s(clip: Clip, tracks: Tracks, leg_px: float) -> float | None:
    """The walker's own step time (s): median of the label-free step times over every stretch of
    walking across the frame, steady or not (it sizes the steadiness window, so it can't need it).
    None with fewer than MIN_TYPICAL_STEPS steps."""
    with np.errstate(invalid="ignore"):
        moving = pelvis_in_view(clip) & (np.abs(pelvis_speed(tracks, leg_px)) >= V_MIN)
    sep = heel_separation(clip, leg_px)
    steps = [
        float(d)
        for a, b in runs(moving)
        for run in contact_runs(sep, Segment(a, b, 1.0), clip.fps)
        for d in np.diff(run)
    ]
    return float(np.median(steps)) if len(steps) >= MIN_TYPICAL_STEPS else None


@dataclass
class Walk:
    fps: float
    contact_runs: list[list[float]] = field(default_factory=list)  # label-free step events, s
    heel_strikes: dict[str, list[int]] = field(default_factory=lambda: {"L": [], "R": []})
    step_times: list[float] = field(default_factory=list)  # between labelled strikes of alternate feet
    step_ends: list[str] = field(default_factory=list)  # foot whose strike ends each labelled step
    stride_times: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})
    hip_excursion: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})
    # Each stride's outline (stride_outline): leading leg "L", the other "R", CURVE_POINTS x 2 per point;
    # and where in the stride (0-1) the other foot struck.
    stride_outlines: list[dict[str, npt.NDArray[np.float64] | None]] = field(default_factory=list)
    trail_strikes: list[float] = field(default_factory=list)
    step_lengths_m: list[float] | None = None
    step_length_times: list[float] = field(default_factory=list)  # step times of the measured lengths

    @property
    def contact_step_times(self) -> list[float]:
        """Label-free step times, s."""
        return [float(d) for run in self.contact_runs for d in np.diff(run)]

    @property
    def step_count(self) -> int:
        return sum(len(run) - 1 for run in self.contact_runs)

    @property
    def mean_step_time(self) -> float:
        """Label-free step time: per run, the mean of its two alternations (steps ending on one foot,
        then the other); runs pooled by step count.

        A constant event timing offset d on one foot makes one alternation t+d and the other t-d.
        When a run holds more of one kind (an odd number of steps), a plain mean is biased; the mean
        of the two alternation means cancels d exactly."""
        total, n = 0.0, 0
        for run in self.contact_runs:
            d = np.diff(run)
            per_step = (d[0::2].mean() + d[1::2].mean()) / 2 if len(d) >= 2 else d[0]
            total += float(per_step) * len(d)
            n += len(d)
        return total / n if n else math.nan

    @property
    def cadence(self) -> float:
        """Steps per minute: 60 / the label-free mean step time."""
        t = self.mean_step_time
        return 60.0 / t if math.isfinite(t) else math.nan

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
    """Events and per-step/per-stride values, pooled over the segments. Without `segments` the
    whole clip is one segment walking the way the feet point (e.g. a walker on a treadmill)."""
    tracks = tracks or build_tracks(clip)
    leg_px = leg_length(tracks)
    walk = Walk(fps=clip.fps, step_lengths_m=[] if calibration else None)
    if not math.isfinite(leg_px) or leg_px <= 0:
        return walk
    if segments is None:
        segments = [Segment(0, clip.n_frames, facing(tracks))]
    sep = heel_separation(clip, leg_px)
    for seg in segments:
        _measure_segment(walk, tracks, sep, seg, leg_px, calibration)
    return walk


def measure_passes(
    clip: Clip,
    segments: list[Segment],
    calibration: Calibration | None = None,
    tracks: Tracks | None = None,
) -> list[Walk]:
    """measure_walk for each walk across the frame (segments sharing a pass_index), in order.
    Nothing crosses a segment boundary, so the passes' values together are measure_walk's."""
    tracks = tracks or build_tracks(clip)
    leg_px = leg_length(tracks)
    if not math.isfinite(leg_px) or leg_px <= 0:
        return []
    sep = heel_separation(clip, leg_px)
    walks: dict[int, Walk] = {}
    for seg in segments:
        walk = walks.setdefault(
            seg.pass_index, Walk(fps=clip.fps, step_lengths_m=[] if calibration else None)
        )
        _measure_segment(walk, tracks, sep, seg, leg_px, calibration)
    return [walks[k] for k in sorted(walks)]


OUTLINE_NAMES = ("hip", "knee", "ankle", "heel", "toe")


def stride_outline(
    tracks: Tracks, lead: str, sl: slice, direction: float, leg_px: float
) -> dict[str, npt.NDArray[np.float64] | None] | None:
    """One stride of both legs (ghost replay): the leading leg (whose heel strikes at 0 and 1) as "L",
    the other as "R"; x relative to the pelvis in the walking direction, y above the lowest visible foot
    point of the stride, both in leg lengths; CURVE_POINTS samples. A point not visible for the whole
    stride is None (never filled in); None for the stride unless the pelvis and the leading leg are."""
    trail = "R" if lead == "L" else "L"
    pts = {
        (role, n): tracks[(side, n)][sl] for role, side in (("L", lead), ("R", trail)) for n in OUTLINE_NAMES
    }
    pelvis = tracks.pelvis[sl]
    ok = {key: bool(np.isfinite(xy).all()) for key, xy in pts.items()}
    if not (np.isfinite(pelvis).all() and all(ok[("L", n)] for n in OUTLINE_NAMES)):
        return None
    floor = max(float(np.max(pts[key][:, 1])) for key in pts if key[1] in ("heel", "toe") and ok[key])
    u = np.linspace(0, 1, len(pelvis))
    grid = np.linspace(0, 1, CURVE_POINTS)
    out: dict[str, npt.NDArray[np.float64] | None] = {}
    for (role, name), xy in pts.items():
        if not ok[(role, name)]:
            out[f"{role}_{name}"] = None
            continue
        x = direction * (xy[:, 0] - pelvis[:, 0]) / leg_px
        y = (floor - xy[:, 1]) / leg_px
        out[f"{role}_{name}"] = np.c_[np.interp(grid, u, x), np.interp(grid, u, y)]
    return out


def _measure_segment(
    walk: Walk,
    tracks: Tracks,
    sep: npt.NDArray[np.float64],
    seg: Segment,
    leg_px: float,
    calibration: Calibration | None,
) -> None:
    """Add one segment's events and values to `walk`."""
    fps = walk.fps
    walk.contact_runs.extend(contact_runs(sep, seg, fps))
    events = sorted([(int(f), side) for side in ("L", "R") for f in heel_strikes(tracks, side, seg, leg_px)])
    for f, side in events:
        walk.heel_strikes[side].append(f)
    # Labelled steps: consecutive strikes of alternate feet.
    for k in range(1, len(events)):
        (f0, s0), (f1, s1) = events[k - 1], events[k]
        dt = (f1 - f0) / fps
        if s0 == s1 or not (STEP_S_RANGE[0] <= dt <= STEP_S_RANGE[1]):
            continue
        walk.step_times.append(dt)
        walk.step_ends.append(s1)
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
            th = thigh_angle(hip, knee, seg.direction)
            walk.hip_excursion[s0].append(float(np.max(th) - np.min(th)))
        outline = stride_outline(tracks, s0, sl, seg.direction, leg_px)
        if outline is not None:
            walk.stride_outlines.append(outline)
            walk.trail_strikes.append((events[k - 1][0] - f0) / (f1 - f0))
