"""Audit unit tests for src/core/calculate_angles.py, activity/cadence and symmetry logic.
Tests marked 'EXPECTED FAIL' encode what a correct implementation must satisfy; they
fail against the current code and are the evidence for audit findings.
Run (repo root): python -m pytest _audit/tests -v
"""
import math, os, sys
import numpy as np, pandas as pd, pytest

sys.path.insert(0, os.getcwd())
from gaitcore.angles import angle_3pts, knee_angle_L, hip_angle_L, shoulder_tilt, add_all_angles
from gaitcore.activity import classify_activity
from gaitcore.legacy import calculate_risk_scores


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
    import mediapipe as mp
    L = mp.solutions.pose.PoseLandmark
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
    MediaPipe returns x/width, y/height; the app takes angles on those directly."""
    W, H = 480, 848
    hip, knee, ankle = (240, 300), (240, 500), (440, 500)   # 90 deg in pixels
    n = lambda p: (p[0] / W, p[1] / H)
    r = row_from({23: n(hip), 25: n(knee), 27: n(ankle)})
    assert knee_angle_L(r) == pytest.approx(90.0, abs=1.0)
    # the axis-aligned case above survives; a diagonal thigh/shank exposes the distortion
    hip, knee, ankle = (240, 300), (340, 480), (240, 660)   # 121.9 deg in pixels
    true = angle_3pts(hip, knee, ankle)
    r = row_from({23: n(hip), 25: n(knee), 27: n(ankle)})
    assert knee_angle_L(r) == pytest.approx(true, abs=1.0), f"true {true:.1f} vs app {knee_angle_L(r):.1f}"

def test_shoulder_tilt_level_shoulders_facing_either_way():
    """EXPECTED FAIL: level shoulders should be 0 deg tilt regardless of walking direction.
    Facing the other way (left shoulder to the right of right shoulder) returns 180."""
    facing_a = row_from({11: (0.4, 0.3), 12: (0.6, 0.3)})
    facing_b = row_from({11: (0.6, 0.3), 12: (0.4, 0.3)})
    assert shoulder_tilt(facing_a) == pytest.approx(0, abs=1)
    assert shoulder_tilt(facing_b) == pytest.approx(0, abs=1)

# ---- cadence -----------------------------------------------------------------
def synthetic_walk(steps_per_min=110, secs=20, fps=30, noise_deg=0.0, seed=0):
    """Knee angles for a walker. One gait cycle per leg = 2 steps.
    Knee angle: ~178 deg in stance, ~118 deg peak swing flexion (60 deg flexion)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, secs, 1 / fps)
    f_leg = steps_per_min / 2 / 60      # cycles per second per leg
    def knee(phase):
        s = (np.sin(2 * np.pi * f_leg * t + phase) + 1) / 2   # 0..1
        return 178 - 60 * s ** 2
    df = pd.DataFrame({"frame": np.arange(len(t)), "time_s": t,
                       "knee_L": knee(0) + rng.normal(0, noise_deg, len(t)),
                       "knee_R": knee(np.pi) + rng.normal(0, noise_deg, len(t)),
                       "hip_L": 170.0, "hip_R": 170.0,
                       "lm27_y": 0.8 + 0.02 * np.sin(2 * np.pi * f_leg * t)})
    return df

def test_cadence_reports_steps_per_minute():
    """EXPECTED FAIL: 110 steps/min walker. App counts left-knee cycles only -> ~55."""
    df = synthetic_walk(110)
    r = calculate_risk_scores(df, activity="Walking")
    assert r["scores"]["cadence"] == pytest.approx(110, rel=0.1), r["scores"]["cadence"]

@pytest.mark.parametrize("noise", [3, 6])
def test_cadence_robust_to_jitter(noise):
    """3 deg passes; 6 deg is EXPECTED FAIL. Measured on the sample clip, frame-to-frame
    knee jumps have median 4.5 deg and p95 24 deg, and there is no smoothing or hysteresis."""
    clean = calculate_risk_scores(synthetic_walk(110), activity="Walking")["scores"]["cadence"]
    noisy = calculate_risk_scores(synthetic_walk(110, noise_deg=noise), activity="Walking")["scores"]["cadence"]
    assert noisy == pytest.approx(clean, rel=0.1), (clean, noisy)

def test_healthy_walker_classified_walking():
    """EXPECTED FAIL: a clean 110 steps/min walk with 60 deg knee flexion."""
    act = classify_activity(synthetic_walk(110))
    assert act["activity"] == "Walking", act

# ---- symmetry ----------------------------------------------------------------
def test_symmetry_index_detects_halved_knee_rom():
    """EXPECTED FAIL: right knee flexes 30 deg vs left 60 deg (50% ROM loss).
    SI computed on MEAN absolute angle (~160 deg) compresses this below the 10% 'mild' cut."""
    df = synthetic_walk(110)
    df["knee_R"] = 178 - (178 - df["knee_R"]) * 0.5
    r = calculate_risk_scores(df, activity="Walking")
    knee = [f for f in r["findings"] if f["metric"] == "Knee Symmetry"][0]
    assert knee["status"] != "good", (r["scores"]["knee_symmetry_index"], knee["status"])
