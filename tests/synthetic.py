"""Synthetic MediaPipe-shaped landmark frames: a side-view stick figure walking.
Never use the real sample clip in tests (privacy rule)."""

import numpy as np
import pandas as pd


def synthetic_landmarks(secs=10.0, fps=30.0, steps_per_min=110.0, knee_scale_R=1.0):
    t = np.arange(0, secs, 1 / fps)
    f = steps_per_min / 2 / 60  # gait cycles per second per leg
    rows = {"frame": np.arange(len(t)), "time_s": np.round(t, 4)}
    for i in range(33):
        rows[f"lm{i}_x"] = np.full(len(t), 0.5)
        rows[f"lm{i}_y"] = np.full(len(t), 0.5)
        rows[f"lm{i}_z"] = np.zeros(len(t))
        rows[f"lm{i}_vis"] = np.full(len(t), 0.99)
    for sh in (11, 12):
        rows[f"lm{sh}_y"] = np.full(len(t), 0.25)
    for side, (hip, knee, ankle), phase, kscale in (
        ("L", (23, 25, 27), 0.0, 1.0),
        ("R", (24, 26, 28), np.pi, knee_scale_R),
    ):
        s = np.sin(2 * np.pi * f * t + phase)
        hip_flex = np.radians(20 * s)  # thigh swing +-20 deg
        knee_flex = np.radians(kscale * 60 * ((s + 1) / 2) ** 2)  # 0..60 deg flexion
        hx, hy = 0.5, 0.5
        kx, ky = hx + 0.2 * np.sin(hip_flex), hy + 0.2 * np.cos(hip_flex)
        a = hip_flex - knee_flex
        ax, ay = kx + 0.2 * np.sin(a), ky + 0.2 * np.cos(a)
        rows[f"lm{hip}_x"], rows[f"lm{hip}_y"] = np.full(len(t), hx), np.full(len(t), hy)
        rows[f"lm{knee}_x"], rows[f"lm{knee}_y"] = kx, ky
        rows[f"lm{ankle}_x"], rows[f"lm{ankle}_y"] = ax, ay
    return pd.DataFrame(rows)
