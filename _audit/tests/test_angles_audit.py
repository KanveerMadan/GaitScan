"""Audit unit tests for the angle, cadence and per-leg knee measurements (originally written
against src/core/calculate_angles.py, activity_classifier.py and risk_scoring.py).
Tests marked 'EXPECTED FAIL' encode what a correct implementation must satisfy; they
fail against the pre-Phase-2 code and are the evidence for audit findings.
Run (repo root): python -m pytest _audit/tests -v

Amended 2026-10-03 for the Rebuild Plan V3 API (approved by Kanveer). Each amended test keeps
its original inputs, expected numbers and tolerances; only the API it calls changed.
Tests for features V3 removes (activity classification, the knee symmetry index) now check
that (a) the removed output is absent from the pipeline and API, and (b) the physical effect
they were meant to detect is still measured. Unamended tests are byte-identical.
"""
import importlib.util, math, os, sys
import numpy as np, pandas as pd, pytest

sys.path.insert(0, os.getcwd())
from gaitcore.angles import angle_3pts, knee_angle_L, hip_angle_L, shoulder_tilt

def row_from(points):
    """points: {landmark_index: (x, y)} -> Series shaped like the app's rows."""
    r = {"frame": 0, "time_s": 0.0}
    for i in range(33):
        x, y = points.get(i, (0.5, 0.5))
        r[f"lm{i}_x"], r[f"lm{i}_y"], r[f"lm{i}_z"], r[f"lm{i}_vis"] = x, y, 0.0, 1.0
    return pd.Series(r)


# ---- pure math -------------------------------------------------------------
@pytest.mark.parametrize("A,B,C,expected", [
    ((0, 1), (0, 0), (1, 0), 90.0),
    ((-1, 0), (0, 0), (1, 0), 180.0),
    ((1, 0), (0, 0), (1, 0), 0.0),
    ((1, 1), (0, 0), (1, 0), 45.0),
    ((1, 0), (0, 0), (-0.5, math.sqrt(3) / 2), 120.0),
])
def test_angle_known_values(A, B, C, expected):
    # 0.1 deg tolerance: the +1e-8 in the denominator biases 0/180 by ~0.01-0.05 deg (negligible)
    assert angle_3pts(A, B, C) == pytest.approx(expected, abs=0.1)

def test_arccos_domain_is_clipped():
    # nearly collinear points whose cosine rounds past -1
    v = angle_3pts((-1e8, 1e-9), (0, 0), (1e8, 0))
    assert not math.isnan(v) and v == pytest.approx(180.0, abs=1e-6)

def test_returns_degrees_not_radians():
    assert angle_3pts((0, 1), (0, 0), (1, 0)) > 3.2

def test_y_axis_inversion_does_not_change_unsigned_angle():
    a = angle_3pts((0.4, 0.3), (0.5, 0.5), (0.45, 0.8))
    b = angle_3pts((0.4, 0.7), (0.5, 0.5), (0.45, 0.2))
    assert a == pytest.approx(b)

def test_degenerate_points_should_be_nan():
    """EXPECTED FAIL: coincident landmarks (e.g. occluded knee collapsed onto hip)
    must not produce a confident angle. Current code returns 90.0."""
    v = angle_3pts((0.5, 0.5), (0.5, 0.5), (0.6, 0.9))
    assert math.isnan(v), f"got {v}"

# ---- landmark wiring ---------------------------------------------------------
def test_left_knee_uses_mediapipe_left_indices():
    from mediapipe.tasks.python.vision import PoseLandmark as L  # mp.solutions is gone in mediapipe 1.0
    assert (L.LEFT_HIP, L.LEFT_KNEE, L.LEFT_ANKLE) == (23, 25, 27)
    assert (L.LEFT_SHOULDER,) == (11,)
    # straight leg -> 180
    r = row_from({23: (0.5, 0.4), 25: (0.5, 0.6), 27: (0.5, 0.8)})
    assert knee_angle_L(r) == pytest.approx(180.0, abs=0.1)

def test_hip_angle_is_trunk_thigh_not_hip_flexion():
    """Documents definition: upright stance with thigh vertical returns 180, so the
    'Hip Flexion' plot is actually 180 - flexion of a trunk-thigh angle."""
    r = row_from({11: (0.5, 0.2), 23: (0.5, 0.5), 25: (0.5, 0.7)})
    assert hip_angle_L(r) == pytest.approx(180.0, abs=0.1)

def test_aspect_ratio_preserves_angle_on_portrait_video():
    """EXPECTED FAIL: a true 90 deg knee in PIXEL space on a 480x848 frame.
    MediaPipe returns x/width, y/height; the angle must be taken after scaling back to pixels."""
    W, H = 480, 848
    hip, knee, ankle = (240, 300), (240, 500), (440, 500)   # 90 deg in pixels
    n = lambda p: (p[0] / W, p[1] / H)
    r = row_from({23: n(hip), 25: n(knee), 27: n(ankle)})
    assert knee_angle_L(r, frame_size=(W, H)) == pytest.approx(90.0, abs=1.0)
    # the axis-aligned case above survives; a diagonal thigh/shank exposes the distortion
    hip, knee, ankle = (240, 300), (340, 480), (240, 660)   # 121.9 deg in pixels
    true = angle_3pts(hip, knee, ankle)
    r = row_from({23: n(hip), 25: n(knee), 27: n(ankle)})
    got = knee_angle_L(r, frame_size=(W, H))
    assert got == pytest.approx(true, abs=1.0), f"true {true:.1f} vs app {got:.1f}"

def test_shoulder_tilt_level_shoulders_facing_either_way():
    """EXPECTED FAIL: level shoulders should be 0 deg tilt regardless of walking direction.
    Facing the other way (left shoulder to the right of right shoulder) returns 180."""
    facing_a = row_from({11: (0.4, 0.3), 12: (0.6, 0.3)})
    facing_b = row_from({11: (0.6, 0.3), 12: (0.4, 0.3)})
    assert shoulder_tilt(facing_a) == pytest.approx(0, abs=1)
    assert shoulder_tilt(facing_b) == pytest.approx(0, abs=1)

# ---- cadence -----------------------------------------------------------------
def synthetic_walk_landmarks(steps_per_min=110, secs=20, fps=30, noise_deg=0.0, seed=0,
                             knee_scale_R=1.0, W=480, H=848):
    """MediaPipe-shaped landmarks (x/W, y/H) of a side-view walker facing +x, pelvis fixed.
    Same gait as the original knee-angle walker: one gait cycle per leg = 2 steps; knee angle
    ~178 deg in stance, ~118 deg at peak swing (60 deg above stance); legs in antiphase.
    noise_deg rotates the shank about the knee, so the knee angle carries exactly the original
    N(0, noise_deg) noise (same seed, same draw order: left, then right). knee_scale_R scales
    (178 - right knee angle), as the original symmetry test did. The thigh swings +-20 deg about
    vertical and is furthest forward when the knee is extended (heel strike)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, secs, 1 / fps)
    f_leg = steps_per_min / 2 / 60      # cycles per second per leg
    THIGH = SHANK = 170.0               # px
    hx, hy = 0.5 * W, 0.45 * H          # hip joint, px
    rows = {"frame": np.arange(len(t)), "time_s": t}
    for i in range(33):
        rows[f"lm{i}_x"], rows[f"lm{i}_y"] = np.full(len(t), 0.5), np.full(len(t), 0.2)
        rows[f"lm{i}_z"], rows[f"lm{i}_vis"] = np.zeros(len(t)), np.ones(len(t))
    for sh in (11, 12):                 # shoulders straight above the hips (side view)
        rows[f"lm{sh}_x"], rows[f"lm{sh}_y"] = np.full(len(t), hx / W), np.full(len(t), (hy - 260) / H)
    noise = {"L": rng.normal(0, noise_deg, len(t)), "R": rng.normal(0, noise_deg, len(t))}
    for side, (hip, knee, ankle, heel, toe), phase in (("L", (23, 25, 27, 29, 31), 0.0),
                                                       ("R", (24, 26, 28, 30, 32), np.pi)):
        s = (np.sin(2 * np.pi * f_leg * t + phase) + 1) / 2          # 0..1
        knee_angle = 178 - 60 * s ** 2
        if side == "R":
            knee_angle = 178 - (178 - knee_angle) * knee_scale_R
        knee_angle = knee_angle + noise[side]
        thigh = np.radians(-20 * np.sin(2 * np.pi * f_leg * t + phase))  # from vertical, +forward
        shank = thigh - np.radians(180 - knee_angle)
        kx, ky = hx + THIGH * np.sin(thigh), hy + THIGH * np.cos(thigh)
        ax, ay = kx + SHANK * np.sin(shank), ky + SHANK * np.cos(shank)
        pts = {hip: (np.full(len(t), hx), np.full(len(t), hy)), knee: (kx, ky), ankle: (ax, ay),
               heel: (ax - 20, ay + 10), toe: (ax + 50, ay + 15)}
        for i, (x, y) in pts.items():
            rows[f"lm{i}_x"], rows[f"lm{i}_y"] = x / W, y / H
    return pd.DataFrame(rows)

def measure(df, fps=30, W=480, H=848):
    from gaitcore.clip import Clip
    from gaitcore.gait import measure_walk
    return measure_walk(Clip(landmarks=df, fps=fps, width=W, height=H))

def test_cadence_reports_steps_per_minute():
    """EXPECTED FAIL: 110 steps/min walker. The pre-V3 app counted left-knee cycles only -> ~55."""
    cadence = measure(synthetic_walk_landmarks(110)).cadence
    assert cadence == pytest.approx(110, rel=0.1), cadence

@pytest.mark.parametrize("noise", [3, 6])
def test_cadence_robust_to_jitter(noise):
    """6 deg was EXPECTED FAIL. Measured on the sample clip, frame-to-frame knee jumps have
    median 4.5 deg and p95 24 deg; the pre-V3 app had no smoothing or hysteresis."""
    clean = measure(synthetic_walk_landmarks(110)).cadence
    noisy = measure(synthetic_walk_landmarks(110, noise_deg=noise)).cadence
    assert noisy == pytest.approx(clean, rel=0.1), (clean, noisy)

# ---- removed outputs (V3 metric policy): absent, but the physical effect is still measured ----
REMOVED_KEYS = {"activity", "confidence", "risk_score", "overall_risk_score", "risk_label",
                "risk_meaning", "risk_color", "knee_symmetry_index", "hip_symmetry_index",
                "knee_si", "hip_si", "findings", "recommendations", "exercises", "mode"}

def _keys(obj):
    if isinstance(obj, dict):
        return set(obj) | set().union(*(_keys(v) for v in obj.values()))
    if isinstance(obj, (list, tuple)):
        return set().union(*(_keys(v) for v in obj))
    return set()

def assert_removed_outputs_absent():
    """Pipeline: the result of analysing the synthetic walker. API: every field name in the
    OpenAPI schema."""
    from gaitcore.clip import Clip
    from gaitcore.pipeline import analyse
    clip = Clip(landmarks=synthetic_walk_landmarks(110), fps=30, width=480, height=848)
    assert not _keys(analyse(clip).to_dict()) & REMOVED_KEYS
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite://")
    from app.main import app
    assert not _keys(app.openapi()) & REMOVED_KEYS

def test_healthy_walker_measured_without_activity_label():
    """EXPECTED FAIL: a clean 110 steps/min walk with 60 deg knee flexion. The pre-V3 app
    labelled it 'Unknown'. V3 removes activity classification; the walk must still be measured."""
    assert importlib.util.find_spec("gaitcore.activity") is None
    assert_removed_outputs_absent()
    w = measure(synthetic_walk_landmarks(110))
    assert w.cadence == pytest.approx(110, rel=0.1), w.cadence

# ---- knee range-of-motion loss on one side ----------------------------------------
def test_halved_knee_rom_is_not_reported_as_a_symmetry_index():
    """The pre-V3 app hid a 50% knee ROM loss in a symmetry index on MEAN absolute angle (7.3%,
    'good'). V3 removed the index; knee angle itself was removed on 2026-11-12 (Phase 8 cancelled,
    so it can never be validated). The walk is still timed, and no knee value is reported."""
    assert_removed_outputs_absent()
    w = measure(synthetic_walk_landmarks(110, knee_scale_R=0.5))
    assert w.cadence == pytest.approx(110, rel=0.1), w.cadence
    assert not hasattr(w, "knee_peak_flexion")
