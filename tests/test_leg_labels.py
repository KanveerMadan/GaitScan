"""The thigh-sensor check (evaluation/leg_labels.py, Phase 11 BE-A1): the sensor's signed sagittal angle
from its quaternions, and its strides, on synthetic recordings with known answers."""

import numpy as np
import pandas as pd
import pytest
from evaluation.leg_labels import sagittal_angle, sensor_strides


def recording(stride_s=1.1, secs=8.0, fs=84.0, flex=28.0, ext=-14.0, tilt_deg=20.0):
    """A thigh swinging about one axis (flexion +28 deg, extension -14 deg per stride), mounted with a
    fixed tilt, as unit quaternions q0..q3 like the MOTI files."""
    t = np.arange(0, secs, 1 / fs)
    phase = 2 * np.pi * t / stride_s
    angle = (flex + ext) / 2 + (flex - ext) / 2 * np.sin(phase)  # deg about the swing axis
    axis = np.array([0.2, 0.9, 0.39])
    axis /= np.linalg.norm(axis)
    half = np.radians(angle) / 2
    swing = np.c_[np.cos(half), np.sin(half)[:, None] * axis]
    m = np.radians(tilt_deg) / 2
    mount = np.array([np.cos(m), np.sin(m), 0.0, 0.0])  # the sensor sits rotated on the thigh
    w1, x1, y1, z1 = mount
    w2, x2, y2, z2 = swing.T
    q = np.c_[
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ]
    return pd.DataFrame({"Timestamp": t, "q0": q[:, 0], "q1": q[:, 1], "q2": q[:, 2], "q3": q[:, 3]}), angle


def test_the_sagittal_angle_follows_the_swing_with_flexion_positive():
    rec, truth = recording()
    a = sagittal_angle(rec)
    assert np.ptp(a) == pytest.approx(np.ptp(truth), abs=0.5)  # 42 deg range
    assert np.corrcoef(a, truth)[0, 1] > 0.999  # same shape and sign, offset free


def test_strides_and_their_range_are_found_one_per_cycle():
    rec, _ = recording(stride_s=1.1)
    strides, roms = sensor_strides(rec)
    assert len(strides) >= 3
    assert np.median(strides) == pytest.approx(1.1, abs=0.02)
    assert np.median(roms) == pytest.approx(42.0, abs=1.0)


def test_a_recording_too_short_for_three_strides_gives_none():
    rec, _ = recording(secs=2.5)
    strides, _ = sensor_strides(rec)
    assert len(strides) < 3
