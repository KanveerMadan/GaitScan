"""Synthetic MediaPipe-shaped landmarks with known ground truth. Never use the real sample clip in
tests (privacy rule).

`synthetic_clip` is an overground walker seen by a fixed camera:
- passes across the frame, with acceleration/deceleration ramps and standing turns in between;
- each heel is fixed on the floor during stance (60% of the cycle) and swings forward with a lift;
- the pelvis height comes from the stance leg(s) (inverted pendulum, leg 98% extended);
- knees by two-link inverse kinematics; everything built in 3D and projected at a camera yaw.

So heel strikes, cadence, step length and speed are known exactly, and the knee and hip angles can be
measured from the generated pixels independently of the code under test.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gaitcore.clip import Clip

THIGH = SHANK = 100.0  # px; leg length L = 200 px
LEG = THIGH + SHANK
HIP_HALF = 0.10 * LEG  # hip joint centres, lateral half-distance
SHOULDER_HALF = 0.20 * LEG
TORSO = 0.54 * LEG  # shoulder height above the hip
ANKLE_UP, ANKLE_FWD, TOE_FWD = 0.04 * LEG, 0.05 * LEG, 0.25 * LEG
STANCE = 0.6
LIFT = 0.10 * LEG
M_PER_PX = 0.9 / LEG  # a 0.9 m leg


@dataclass
class Truth:
    heel_strikes: dict[str, list[float]] = field(default_factory=lambda: {"L": [], "R": []})  # s
    steady: list[tuple[float, float]] = field(default_factory=list)  # constant-speed spans, s
    cadence: float = 0.0  # steps/min
    step_length_m: float = 0.0
    speed_m_s: float = 0.0
    floor_y: float = 0.0  # px, image row of the floor at the walking line


def _profile(t, pass_secs, ramp, turn):
    """Signed walking speed (fraction of steady) and the pass index, for each time."""
    period = pass_secs + turn
    k = np.floor(t / period).astype(int)
    u = t - k * period
    mag = np.clip(np.minimum(u / ramp, (pass_secs - u) / ramp), 0, 1) * (u < pass_secs)
    return np.where(k % 2 == 0, 1.0, -1.0) * mag, k, u


def synthetic_clip(
    steps_per_min=110.0,
    passes=3,
    pass_secs=4.0,
    ramp_secs=0.8,
    turn_secs=1.5,
    fps=30.0,
    width=1280,
    height=720,
    step_ratio=0.6,  # step length / leg length
    yaw_deg=0.0,
    noise_px=0.0,
    seed=0,
    people=1,
    rotate90=False,
    feet_visibility=0.95,
    far_visibility=0.8,
) -> tuple[Clip, Truth]:
    rng = np.random.default_rng(seed)
    step_t = 60.0 / steps_per_min
    T = 2 * step_t
    s = step_ratio * LEG  # steady step length, px
    v = s / step_t  # steady speed, px/s
    total = passes * pass_secs + (passes - 1) * turn_secs
    t = np.arange(0, total, 1 / fps)
    n = len(t)

    # Pelvis path: integrate the speed profile on a fine grid.
    fine = np.arange(0, total + 1, 1e-3)
    prof, _, _ = _profile(fine, pass_secs, ramp_secs, turn_secs)
    x_fine = np.cumsum(prof * v) * 1e-3
    x_fine += (width - (x_fine.max() - x_fine.min())) / 2 - x_fine.min()
    px = np.interp(t, fine, x_fine)
    prof_t, k_t, _ = _profile(t, pass_secs, ramp_secs, turn_secs)
    direction = np.where(k_t % 2 == 0, 1.0, -1.0)

    truth = Truth(cadence=steps_per_min, step_length_m=s * M_PER_PX, speed_m_s=v * M_PER_PX)
    for k in range(passes):
        a = k * (pass_secs + turn_secs)
        truth.steady.append((a + ramp_secs, a + pass_secs - ramp_secs))

    # Heel strike times per leg: continuous cadence while moving; left leads.
    feet = {}
    for side, offset in (("L", 0.0), ("R", step_t)):
        hs = []
        for k in range(passes):
            a = k * (pass_secs + turn_secs)
            tt = a + offset + step_t / 2
            while tt < a + pass_secs - step_t / 2:
                hs.append(tt)
                tt += T
        truth.heel_strikes[side] = hs
        # Landing point: half a step ahead of the pelvis in the direction of travel (scaled by speed).
        period = pass_secs + turn_secs
        d = np.array([1.0 if int(h // period) % 2 == 0 else -1.0 for h in hs])
        land = np.interp(hs, fine, x_fine) + d * np.abs(np.interp(hs, fine, prof)) * s / 2
        # Heel x over time: fixed in stance; (1 - cos) swing from toe-off to the next landing,
        # lifted only for a normal-length swing (a slow shuffle during turns stays on the floor).
        hx = np.full(n, land[0])
        lift = np.zeros(n)
        hs_arr = np.array(hs)
        for i, ti in enumerate(t):
            j = np.searchsorted(hs_arr, ti, side="right") - 1
            if j < 0:
                continue
            off = hs[j] + STANCE * T
            if ti <= off or j + 1 >= len(hs):
                hx[i] = land[j]
                continue
            u = (ti - off) / (hs[j + 1] - off)
            hx[i] = land[j] + (land[j + 1] - land[j]) * (1 - np.cos(np.pi * u)) / 2
            if hs[j + 1] - off <= T:
                lift[i] = LIFT * np.sin(np.pi * u)
        feet[side] = (hx, lift)

    floor = height * 0.85
    truth.floor_y = floor
    # Pelvis height from the stance leg(s): inverted pendulum with the leg 98% extended.
    reach = 0.98 * LEG
    hy = np.full(n, np.inf)
    for side in ("L", "R"):
        hx, lift = feet[side]
        stance = lift == 0
        dx = np.clip(np.abs(hx + direction * ANKLE_FWD - px), 0, reach * 0.95)
        h = np.sqrt(reach**2 - dx**2) + ANKLE_UP
        hy = np.where(stance, np.minimum(hy, h), hy)
    hy = np.where(np.isfinite(hy), hy, reach + ANKLE_UP)
    pelvis_y = floor - hy

    # Turning: body yaw rotates by 180 deg during each turn (frontal at mid-turn).
    _, _, u_t = _profile(t, pass_secs, ramp_secs, turn_secs)
    turning = u_t >= pass_secs
    body = np.where(turning, np.pi * (u_t - pass_secs) / max(turn_secs, 1e-9), 0.0)
    lateral = np.where(k_t % 2 == 0, 1.0, -1.0) * np.cos(body)  # left side towards +z when walking +x
    yaw = np.radians(yaw_deg)
    face_x = direction * np.cos(body)  # forward component of the facing direction

    cx = width / 2

    def proj(x_world, z_world):
        # camera yaw: image x = x cos(yaw) + z sin(yaw), about the frame centre
        return cx + (x_world - cx) * np.cos(yaw) + z_world * np.sin(yaw)

    pts = {}
    for side, zs in (("L", 1.0), ("R", -1.0)):
        hx, lift = feet[side]
        z = zs * HIP_HALF * lateral
        hip = (px, pelvis_y)
        heel = (hx, floor - lift)
        ankle = (hx + face_x * ANKLE_FWD, floor - lift - ANKLE_UP)
        toe = (hx + face_x * TOE_FWD, floor - lift)
        dxa, dya = ankle[0] - hip[0], ankle[1] - hip[1]
        d = np.minimum(np.hypot(dxa, dya), 0.999 * LEG)
        mx, my = hip[0] + dxa / 2, hip[1] + dya / 2
        hgt = np.sqrt(np.maximum(THIGH**2 - (d / 2) ** 2, 0))
        nx, ny = -dya / np.hypot(dxa, dya), dxa / np.hypot(dxa, dya)  # unit normal
        sgn = np.sign(nx * np.where(face_x == 0, 1, face_x))  # knee bends towards the facing side
        sgn = np.where(sgn == 0, 1, sgn)
        knee = (mx + sgn * hgt * nx, my + sgn * hgt * ny)
        for name, (x, y) in (("hip", hip), ("knee", knee), ("ankle", ankle), ("heel", heel), ("toe", toe)):
            pts[(side, name)] = (proj(x, z), y)
        sh_z = zs * SHOULDER_HALF * lateral
        pts[(side, "shoulder")] = (proj(px, sh_z), pelvis_y - TORSO)

    idx = {
        ("L", "shoulder"): 11,
        ("R", "shoulder"): 12,
        ("L", "hip"): 23,
        ("R", "hip"): 24,
        ("L", "knee"): 25,
        ("R", "knee"): 26,
        ("L", "ankle"): 27,
        ("R", "ankle"): 28,
        ("L", "heel"): 29,
        ("R", "heel"): 30,
        ("L", "toe"): 31,
        ("R", "toe"): 32,
    }
    cols = {}
    for i in range(33):  # head/arms: a point above the shoulders (unused by the pipeline)
        cols[f"lm{i}_x"] = proj(px, 0.0)
        cols[f"lm{i}_y"] = pelvis_y - TORSO - 0.2 * LEG
        cols[f"lm{i}_z"] = np.zeros(n)
        cols[f"lm{i}_vis"] = np.full(n, 0.99)
    # The camera stays on one side, so the far leg is R on even passes and L after each turn.
    far = np.where(k_t % 2 == 0, "R", "L")
    for (side, name), i in idx.items():
        x, y = pts[(side, name)]
        cols[f"lm{i}_x"] = x + rng.normal(0, noise_px, n)
        cols[f"lm{i}_y"] = y + rng.normal(0, noise_px, n)
        vis = np.full(n, feet_visibility if name in ("ankle", "heel", "toe") else 0.99)
        if name not in ("shoulder", "hip"):
            vis = np.where(far == side, np.minimum(vis, far_visibility), vis)
        cols[f"lm{i}_vis"] = vis
    df = pd.DataFrame(cols)
    W, H = width, height
    if rotate90:  # the phone recorded the scene rotated by 90 deg clockwise
        xs = [c for c in df if c.endswith("_x")]
        for c in xs:
            yc = c[:-2] + "_y"
            df[c], df[yc] = H - df[yc], df[c].copy()
        W, H = H, W
    for c in df:
        if c.endswith("_x"):
            df[c] = df[c] / W
        elif c.endswith("_y"):
            df[c] = df[c] / H
    df["n_poses"] = people
    return Clip(landmarks=df, fps=fps, width=W, height=H), truth


def knee_flexion_truth(clip: Clip, side: str) -> np.ndarray:
    """Pixel-space knee flexion (180 - interior angle) computed directly from the landmarks."""
    hip, knee, ankle = (23, 25, 27) if side == "L" else (24, 26, 28)
    lm = clip.landmarks

    def p(i):
        return np.c_[lm[f"lm{i}_x"] * clip.width, lm[f"lm{i}_y"] * clip.height]

    u, w = p(hip) - p(knee), p(ankle) - p(knee)
    cos = (u * w).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(w, axis=1)
    return 180 - np.degrees(np.arccos(np.clip(cos, -1, 1)))
