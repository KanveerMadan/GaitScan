"""Label-free joint movement and gait phases (Plan V3 Phase 11, owner decision B, 2026-11-14).

MediaPipe's left/right leg labels can't be trusted (docs/validation/leg-labels.md: on LJMU they often
follow the legs' position in the image, and brief swaps are common), so no value here depends on them.
Each stride's leg is found from foot motion and footprints instead:

- Step events are the label-free heel-separation peaks (gait.contact_runs), validated on LJMU. A peak
  marks the middle of double support, not the strike, so the strike is found from foot motion in each
  frame, without labels: the **heel strike** is where the front heel (the heel furthest ahead of the
  pelvis, whichever label it carries) stops moving in the image, below PLANTED leg lengths per second,
  just before the step event. The camera must be still (the capture protocol: a tripod or a propped
  phone). The front heel there is the striking leg, and its position is the footprint.
- From that strike to the next step event, the leg stands on its footprint: in each frame it is the
  leg chain whose heel is nearest the footprint. If both heels are within TIE_LEGS of it (the swinging
  foot passing), the straighter knee is the standing leg.
- From the next step event to the leg's own next strike, the other leg stands on the new footprint, so
  the leg is the chain whose heel is furthest from it (if tied, the more bent knee: it is swinging).
- **Toe-off**: after the other foot lands, where the rear toe (the toe furthest behind the pelvis)
  starts moving faster than PLANTED.
(Zeni et al. 2008's heel-ahead-of-pelvis rule, used by gait.py for labelled strikes, times the strike
early when the heel slows down over the whole late swing; foot speed doesn't depend on that.)

A chain is the knee, ankle, heel and toe MediaPipe gives one label in a frame; MediaPipe swaps whole
legs (gait.py), so a chain is one physical leg in that frame, whichever label it carries. The hip
joint is the pelvis midpoint (in a side view the two hips overlap). Values are for both legs pooled:
which leg is the left one isn't known (per-side values wait for the leg-identity check, decision A).

Angle conventions (sagittal, in the image of a side-on camera; flexion and dorsiflexion positive, as in
Fukuchi et al. 2018, PeerJ 6:e4640):
- knee flexion: 180 - the pelvis-knee-ankle angle (0 = straight);
- hip flexion: the thigh (pelvis -> knee) against the trunk line (shoulders -> pelvis), + when the knee
  is ahead. 2D has no pelvis segment, so this differs from a 3D hip angle by the pelvic tilt;
- ankle: the shank (knee -> ankle) against the foot (heel -> toe), - 90, + = dorsiflexion;
- trunk lean: shoulders -> pelvis line against vertical, + = shoulders ahead;
- arm swing: shoulder -> wrist against vertical; per stride, the furthest forward minus the furthest back
  over both arms;
- thigh angle: the thigh against vertical, + = knee ahead (what a thigh-worn sensor measures);
- pelvis oscillation: vertical range of the pelvis per stride, in leg lengths.
None of these is validated against a reference yet (Phase 11 docs/validation/).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from gaitcore.clip import Clip
from gaitcore.gait import contact_runs, heel_separation, leg_length
from gaitcore.segments import Segment
from gaitcore.signals import SIDES, Tracks, lowpass, masked_xy

Array = npt.NDArray[np.float64]

CURVE_POINTS = 101  # 0-100% of the stride, heel strike to heel strike
MIN_STRIDES = 3  # a median of >= 3 strides can't be set by one bad stride (result.MIN_STRIDES_PER_LEG)
TIE_LEGS = 0.08  # heels this close to the footprint (leg lengths) are told apart by the knee instead
STRIKE_SEARCH = 0.4  # of a step time, before a step event, to find the heel strike
PLANTED = 0.25  # leg lengths per second: a foot slower than this is on the floor (swing ~3, walking ~1.2)
ARM_DOWN_DEG = 60.0  # an arm more than this far from hanging down isn't an arm swing (or isn't an arm)
WRISTS = (15, 16)  # MediaPipe Pose left and right wrist
JOINTS = ("knee", "hip", "ankle")


@dataclass
class Stride:
    """One stride of one (unnamed) leg, heel strike to heel strike."""

    start: int
    end: int  # the leg's next heel strike (frame)
    direction: float
    toe_off: int | None
    knee: Array  # per frame, start..end inclusive
    hip: Array
    ankle: Array
    thigh: Array  # thigh against vertical (for checking against a thigh-worn sensor)
    pelvis_y: Array
    arm_swing: float | None = None

    @property
    def stance_pct(self) -> float | None:
        return None if self.toe_off is None else 100 * (self.toe_off - self.start) / (self.end - self.start)

    @property
    def knee_ic(self) -> float:
        return float(self.knee[0])

    @property
    def knee_peak_swing(self) -> float | None:
        return None if self.toe_off is None else float(np.max(self.knee[self.toe_off - self.start :]))

    @property
    def hip_peak_ext(self) -> float | None:
        return None if self.toe_off is None else float(np.min(self.hip[: self.toe_off - self.start + 1]))

    def curve(self, joint: str) -> Array:
        v = getattr(self, joint)
        return np.asarray(
            np.interp(np.linspace(0, len(v) - 1, CURVE_POINTS), np.arange(len(v)), v), dtype=float
        )


@dataclass
class Kinematics:
    strides: list[Stride] = field(default_factory=list)
    double_support: list[float] = field(default_factory=list)  # % of the stride
    trunk_lean: list[float] = field(default_factory=list)  # deg, per frame of steady walking
    leg_px: float = math.nan

    def summary(self) -> dict[str, dict[str, Any] | None]:
        s = self.strides
        per_stride: dict[str, list[float | None]] = {
            "stance_pct": [x.stance_pct for x in s],
            "knee_ic": [x.knee_ic for x in s],
            "knee_peak_swing": [x.knee_peak_swing for x in s],
            "knee_rom": [float(np.ptp(x.knee)) for x in s],
            "hip_peak_ext": [x.hip_peak_ext for x in s],
            "hip_peak_flex": [float(np.max(x.hip)) for x in s],
            "hip_rom": [float(np.ptp(x.hip)) for x in s],
            "ankle_ic": [float(x.ankle[0]) for x in s],
            "ankle_rom": [float(np.ptp(x.ankle)) for x in s],
            "thigh_rom": [float(np.ptp(x.thigh)) for x in s],
            "pelvis_oscillation": [float(np.ptp(x.pelvis_y)) / self.leg_px for x in s],
            "arm_swing_deg": [x.arm_swing for x in s],
        }
        out: dict[str, dict[str, Any] | None] = {k: _stat(v) for k, v in per_stride.items()}
        stance = out["stance_pct"]
        out["swing_pct"] = None if stance is None else {**stance, "value": 100 - stance["value"]}
        out["double_support_pct"] = _stat(self.double_support)
        lean = [v for v in self.trunk_lean if math.isfinite(v)]
        out["trunk_lean_deg"] = (
            {"value": float(np.mean(lean)), "sd": float(np.std(lean)), "n": len(s)}
            if lean and len(s) >= MIN_STRIDES
            else None
        )
        return out

    def curves(self) -> dict[str, dict[str, Any] | None]:
        out: dict[str, dict[str, Any] | None] = {}
        for joint in JOINTS:
            c = np.array([x.curve(joint) for x in self.strides])
            out[joint] = (
                {"mean": c.mean(axis=0).tolist(), "sd": c.std(axis=0).tolist(), "n": len(c)}
                if len(c) >= MIN_STRIDES
                else None
            )
        return out


def _stat(values: Sequence[float | None]) -> dict[str, Any] | None:
    v = [float(x) for x in values if x is not None and math.isfinite(x)]
    if len(v) < MIN_STRIDES:
        return None
    return {"value": float(np.median(v)), "sd": float(np.std(v, ddof=1)), "n": len(v)}


def _signed(a: Array, b: Array, d: float) -> Array:
    """Angle of b against a in degrees, + when b points further along the walking direction d (image y
    points down, so a turn towards +x reads negative)."""
    ang = np.degrees(np.arctan2(b[:, 1], b[:, 0]) - np.arctan2(a[:, 1], a[:, 0]))
    return np.asarray(-d * ((ang + 180) % 360 - 180))


def _between(u: Array, w: Array) -> Array:
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = (u * w).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(w, axis=1)
    return np.asarray(np.degrees(np.arccos(np.clip(cos, -1, 1))))


LEG_POINTS = ("knee", "ankle", "heel", "toe")


def _raw_chains(clip: Clip, tracks: Tracks, d: float) -> dict[str, dict[str, Array]]:
    """Per labelled chain, unfiltered (a 1-2 frame label swap must not be smeared into its neighbours
    before the legs are untangled): the leg points, and what the untangling needs."""
    pelvis = tracks.pelvis
    out = {}
    for side in ("L", "R"):
        pts = {n: masked_xy(clip, SIDES[side][n]) for n in LEG_POINTS}
        out[side] = {
            **pts,
            "knee_flex": 180 - _between(pelvis - pts["knee"], pts["ankle"] - pts["knee"]),
            "heel_fwd": (pts["heel"][:, 0] - pelvis[:, 0]) * d,
        }
    return out


def _front_heel_speed(ch: dict[str, dict[str, Array]], fps: float, leg_px: float) -> Array:
    """Per frame, without labels: the image speed (leg lengths per second) of the front heel, the heel
    furthest ahead of the pelvis. Backward difference: a heel is still in the frame it lands in."""
    fwd = np.stack([ch["L"]["heel_fwd"], ch["R"]["heel_fwd"]])
    xs = np.stack([ch["L"]["heel"][:, 0], ch["R"]["heel"][:, 0]])
    both = np.isfinite(fwd).all(axis=0)
    idx = np.argmax(np.where(both, fwd, 0.0), axis=0)
    x = np.where(both, xs[idx, np.arange(xs.shape[1])], np.nan)
    return np.asarray(np.abs(np.diff(x, prepend=np.nan)) * fps / leg_px)


def _heel_strike(speed: Array, c: int, step: float, seg: Segment) -> int:
    """The frame where the front heel last stopped (fell below PLANTED) before step event c."""
    lo = max(seg.start, c - max(1, int(round(STRIKE_SEARCH * step))))
    for f in range(c, lo, -1):
        if math.isfinite(speed[f - 1]) and speed[f - 1] > PLANTED and not speed[f] > PLANTED:
            return f
    return c


def _untangle(ch: dict[str, dict[str, Array]], frames: list[int], tie: float) -> Array | None:
    """For frames[0]..frames[-1]: which labelled chain (0 = "L", 1 = "R") is leg P, the leg striking at
    frames[0], frames[2], ...; the other chain is leg Q. In each step interval [c_k, c_k+1) the leg that
    struck at c_k stands on its footprint (its heel there), so it's the chain whose heel is nearest; if
    both heels are within `tie` of it (the other foot passing), the straighter knee. None if a frame
    lacks a heel."""
    c0, cm = frames[0], frames[-1]
    pick = np.zeros(cm - c0 + 1, dtype=int)
    for k in range(len(frames) - 1):
        a, b = frames[k], frames[k + 1]
        striking = [ch[s]["heel_fwd"][a] for s in ("L", "R")]
        if not all(math.isfinite(v) for v in striking):
            return None
        stance0 = int(np.argmax(striking))
        footprint = ch[("L", "R")[stance0]]["heel"][a, 0]
        for f in range(a, b if k < len(frames) - 2 else b + 1):
            dist = [abs(ch[s]["heel"][f, 0] - footprint) for s in ("L", "R")]
            if not all(math.isfinite(v) for v in dist):
                return None
            if abs(dist[0] - dist[1]) < tie:
                knees = [ch[s]["knee_flex"][f] for s in ("L", "R")]
                stance = int(np.nanargmin(knees)) if np.isfinite(knees).any() else stance0
            else:
                stance = int(np.argmin(dist))
            pick[f - c0] = stance if k % 2 == 0 else 1 - stance
    return pick


def _leg_tracks(
    ch: dict[str, dict[str, Array]], pick: Array, c0: int, n: int, fps: float
) -> list[dict[str, Array]]:
    """Untangled tracks of legs P and Q over the run, then the pipeline's 6 Hz low-pass."""
    legs = []
    for leg in (0, 1):
        chosen = pick if leg == 0 else 1 - pick
        out = {}
        for name in LEG_POINTS:
            xy = np.full((n, 2), np.nan)
            rows = np.arange(c0, c0 + len(pick))
            xy[rows] = np.where((chosen == 0)[:, None], ch["L"][name][rows], ch["R"][name][rows])
            out[name] = lowpass(xy, fps)
        legs.append(out)
    return legs


def _angles(leg: dict[str, Array], pelvis: Array, shoulders: Array, d: float) -> dict[str, Array]:
    knee, ankle, heel, toe = (leg[n] for n in LEG_POINTS)
    return {
        "knee": 180 - _between(pelvis - knee, ankle - knee),
        "hip": _signed(pelvis - shoulders, knee - pelvis, d),
        "ankle": 90 - _between(ankle - knee, toe - heel),
        "thigh": _signed(np.tile([0.0, 1.0], (len(knee), 1)), knee - pelvis, d),
        "toe_x": toe[:, 0],
    }


def _mean_visible(a: Array, b: Array) -> Array:
    """The mean of the two points where both are visible, the visible one otherwise (as the pelvis)."""
    both = np.stack([a, b])
    n = np.isfinite(both[:, :, 0]).sum(axis=0)
    total = np.where(np.isfinite(both), both, 0.0).sum(axis=0)
    return np.where(n[:, None] > 0, total / np.maximum(n, 1)[:, None], np.nan)


def _arm_angles(clip: Clip, tracks: Tracks, d: float) -> list[Array]:
    arms = []
    for side, w in zip(("L", "R"), WRISTS, strict=True):
        v = masked_xy(clip, w) - tracks[(side, "shoulder")]
        a = np.degrees(np.arctan2(v[:, 0] * d, v[:, 1]))  # + = wrist ahead; 0 = hanging straight down
        arms.append(np.where(np.abs(a) <= ARM_DOWN_DEG, a, np.nan))
    return arms


def measure_kinematics(clip: Clip, segments: list[Segment], tracks: Tracks) -> Kinematics:
    leg_px = leg_length(tracks)
    k = Kinematics(leg_px=leg_px)
    if not math.isfinite(leg_px) or leg_px <= 0:
        return k
    sep = heel_separation(clip, leg_px)
    tie = TIE_LEGS * leg_px
    pelvis = tracks.pelvis
    shoulders = _mean_visible(tracks[("L", "shoulder")], tracks[("R", "shoulder")])
    for seg in segments:
        d = seg.direction
        ch = _raw_chains(clip, tracks, d)
        speed = _front_heel_speed(ch, clip.fps, leg_px)
        arms = _arm_angles(clip, tracks, d)
        f = np.arange(seg.start, seg.end)
        up = pelvis[f] - shoulders[f]
        k.trunk_lean.extend(np.degrees(np.arctan2(-up[:, 0] * d, up[:, 1])).tolist())
        for run in contact_runs(sep, seg, clip.fps):
            step = float(np.median(np.diff(run))) * clip.fps
            frames = [_heel_strike(speed, int(round(t * clip.fps)), step, seg) for t in run]
            if len(frames) < 3 or any(b <= a for a, b in zip(frames, frames[1:], strict=False)):
                continue
            pick = _untangle(ch, frames, tie)
            if pick is None:
                continue
            legs = [
                _angles(leg, pelvis, shoulders, d)
                for leg in _leg_tracks(ch, pick, frames[0], clip.n_frames, clip.fps)
            ]
            toe_offs: dict[int, int | None] = {}
            for i in range(len(frames) - 2):
                stride = _stride(legs[i % 2], pelvis, frames, i, d, arms, clip.fps, leg_px)
                if stride is not None:
                    k.strides.append(stride)
                    toe_offs[i] = stride.toe_off
            for i in range(1, len(frames) - 2):
                a, b = toe_offs.get(i - 1), toe_offs.get(i)
                if a is not None and b is not None:
                    span = frames[i + 2] - frames[i]
                    k.double_support.append(100 * ((a - frames[i]) + (b - frames[i + 1])) / span)
    return k


def _stride(
    leg: dict[str, Array],
    pelvis: Array,
    frames: list[int],
    i: int,
    d: float,
    arms: list[Array],
    fps: float,
    leg_px: float,
) -> Stride | None:
    c0, c1, c2 = frames[i], frames[i + 1], frames[i + 2]
    rows = np.arange(c0, c2 + 1)
    series = {n: leg[n][rows] for n in ("knee", "hip", "ankle", "thigh")}
    pelvis_y = pelvis[rows, 1]
    if not all(np.isfinite(v).all() for v in (*series.values(), pelvis_y)):
        return None
    # Toe-off: after the other foot lands, where this leg's toe starts moving (backward difference).
    toe = leg["toe_x"]
    moving = [
        f
        for f in range(c1, c2)
        if math.isfinite(toe[f] - toe[f - 1]) and abs(toe[f] - toe[f - 1]) * fps / leg_px > PLANTED
    ]
    swing = None
    both = np.concatenate([arms[0][rows], arms[1][rows]])
    if np.isfinite(both).mean() >= 0.8:
        swing = float(np.nanmax(both) - np.nanmin(both))
    return Stride(
        start=c0,
        end=c2,
        direction=d,
        toe_off=moving[0] if moving else None,  # the first frame off the floor, as heel strike's first on it
        knee=series["knee"],
        hip=series["hip"],
        ankle=series["ankle"],
        thigh=series["thigh"],
        pelvis_y=pelvis_y,
        arm_swing=swing,
    )
