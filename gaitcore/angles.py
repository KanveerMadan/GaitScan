"""2D joint angles (ADR-006, audit F25/F33/F34/F42).

Angles are taken in pixel space: MediaPipe returns x / width and y / height, so on a non-square frame
angles computed on the normalised values are distorted (a true 121.9 deg read 91.1 deg on 480x848).
Coincident points have no angle and return NaN instead of a confident 90 deg.
"""

import numpy as np
import numpy.typing as npt
import pandas as pd

Point = tuple[float, float]
FrameSize = tuple[float, float]
Array = npt.NDArray[np.float64]


def angle_3pts(A: Point, B: Point, C: Point) -> float:
    """Angle at B in degrees between BA and BC; NaN if either vector has zero length."""
    BA = np.asarray(A, dtype=float) - np.asarray(B, dtype=float)
    BC = np.asarray(C, dtype=float) - np.asarray(B, dtype=float)
    norm = float(np.linalg.norm(BA) * np.linalg.norm(BC))
    if norm == 0.0:
        return float("nan")
    return float(np.degrees(np.arccos(np.clip(np.dot(BA, BC) / norm, -1.0, 1.0))))


def _p(row: "pd.Series[float]", i: int, frame_size: FrameSize | None) -> Point:
    """Landmark i of a row, scaled to pixels when the frame size is given."""
    w, h = frame_size or (1.0, 1.0)
    return (float(row[f"lm{i}_x"]) * w, float(row[f"lm{i}_y"]) * h)


def knee_angle_L(row: "pd.Series[float]", frame_size: FrameSize | None = None) -> float:
    return angle_3pts(_p(row, 23, frame_size), _p(row, 25, frame_size), _p(row, 27, frame_size))


def knee_angle_R(row: "pd.Series[float]", frame_size: FrameSize | None = None) -> float:
    return angle_3pts(_p(row, 24, frame_size), _p(row, 26, frame_size), _p(row, 28, frame_size))


def hip_angle_L(row: "pd.Series[float]", frame_size: FrameSize | None = None) -> float:
    """Trunk-thigh angle (shoulder-hip-knee), 180 when upright. Not reported: see thigh_angle."""
    return angle_3pts(_p(row, 11, frame_size), _p(row, 23, frame_size), _p(row, 25, frame_size))


def hip_angle_R(row: "pd.Series[float]", frame_size: FrameSize | None = None) -> float:
    return angle_3pts(_p(row, 12, frame_size), _p(row, 24, frame_size), _p(row, 26, frame_size))


def shoulder_tilt(row: "pd.Series[float]", frame_size: FrameSize | None = None) -> float:
    """Inclination of the shoulder line from horizontal, 0-90 deg, whichever way the person faces.

    A frontal-plane quantity: never reported (V3 metric policy). Kept as a tested helper.
    """
    (x1, y1), (x2, y2) = _p(row, 11, frame_size), _p(row, 12, frame_size)
    if x1 == x2 and y1 == y2:
        return float("nan")
    return float(np.degrees(np.arctan2(abs(y2 - y1), abs(x2 - x1))))


def segment_angle(top: Array, bottom: Array, direction: Array | float) -> Array:
    """Angle of the segment top->bottom from the downward vertical, in degrees, positive when the
    bottom end is ahead of the top end in the walking `direction` (+1 = image +x, -1 = image -x).
    Inputs are (n, 2) pixel arrays (image y points down)."""
    d = bottom - top
    return np.degrees(np.arctan2(np.asarray(direction) * d[:, 0], d[:, 1]))


def thigh_angle(hip: Array, knee: Array, direction: Array | float) -> Array:
    """Sagittal thigh angle from vertical (+ = knee ahead of hip). The V3 'hip sagittal angle'."""
    return segment_angle(hip, knee, direction)


def knee_flexion(hip: Array, knee: Array, ankle: Array, direction: Array | float) -> Array:
    """Signed knee flexion in degrees: thigh angle minus shank angle. 0 = straight leg; equals
    180 - interior angle when flexed; negative when the knee is hyperextended."""
    f = thigh_angle(hip, knee, direction) - segment_angle(knee, ankle, direction)
    return (f + 180.0) % 360.0 - 180.0
