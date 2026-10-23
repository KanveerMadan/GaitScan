"""Measurement core v2 on synthetic ground truth (Plan V3 Phase 2, ADR-006).

All inputs are synthetic (tests/synthetic.py); results are synthetic-ground-truth checks, not
accuracy against real people (that is Phase 3).
"""

import math

import numpy as np
import pytest
from synthetic import M_PER_PX, knee_flexion_truth, synthetic_clip

from gaitcore import quality
from gaitcore.calibration import Calibration, CalibrationError
from gaitcore.gait import leg_length, measure_walk
from gaitcore.pipeline import analyse
from gaitcore.segments import steady_segments
from gaitcore.signals import build_tracks, lowpass, masked_xy


def walk_of(clip, calibration=None):
    tracks = build_tracks(clip)
    segs = steady_segments(clip, tracks, leg_length(tracks))
    return measure_walk(clip, segs, calibration, tracks=tracks), segs


# ---- masking and filtering -------------------------------------------------------------------
def test_low_visibility_landmarks_are_masked_and_never_filled():
    clip, _ = synthetic_clip()
    lm = clip.landmarks
    lm.loc[200:204, "lm25_vis"] = 0.3  # left knee hidden for 5 frames
    xy = masked_xy(clip, 25)
    assert np.isnan(xy[200:205]).all() and np.isfinite(xy[195:200]).all()
    tracks = build_tracks(clip)
    assert np.isnan(tracks[("L", "knee")][200:205]).all()  # no interpolation across the gap


def test_strides_touching_a_masked_frame_give_no_knee_value():
    clip, _ = synthetic_clip()
    full, _ = walk_of(clip)
    clip.landmarks.loc[:, "lm25_vis"] = np.where(np.arange(clip.n_frames) % 20 == 0, 0.3, 0.99)
    gappy, _ = walk_of(clip)
    assert full.knee_peak_flexion["L"]
    assert gappy.knee_peak_flexion["L"] == []  # every stride (> 20 frames) contains a masked frame


def test_frames_with_two_people_are_masked():
    clip, _ = synthetic_clip()
    clip.landmarks.loc[100:110, "n_poses"] = 2
    assert np.isnan(masked_xy(clip, 29)[100:111]).all()


def test_lowpass_keeps_the_gait_signal_and_reduces_frame_noise():
    """A smooth gait-like trajectory: the first 5 harmonics of a 110 steps/min stride (0.92 Hz, up
    to 4.6 Hz), 100 px peak-to-peak, sampled at 30 fps. (The IK walker is not used here: its knee
    locks straight with a corner no real knee has.)"""
    fps, f = 30.0, 110 / 120
    t = np.arange(0, 10, 1 / fps)
    rng = np.random.default_rng(0)
    amps, phases = [50, 20, 10, 5, 3], rng.uniform(0, 2 * np.pi, 5)
    x = sum(
        a * np.sin(2 * np.pi * (k + 1) * f * t + p) for k, (a, p) in enumerate(zip(amps, phases, strict=True))
    )
    clean = np.c_[x, x / 2]
    mid = slice(30, -30)  # away from the run edges
    # The 4th/5th harmonics (3.7/4.6 Hz) are attenuated ~12-26%: error stays < 2% of the range.
    assert np.max(np.abs(lowpass(clean, fps) - clean)[mid]) < 0.02 * np.ptp(x)
    noise = rng.normal(0, 3, clean.shape)
    resid = lowpass(clean + noise, fps) - clean
    assert np.sqrt(np.mean(resid[mid] ** 2)) < 0.7 * np.sqrt(np.mean(noise[mid] ** 2))


def test_lowpass_drops_runs_too_short_to_filter():
    xy = np.full((40, 2), np.nan)
    xy[5:9] = 1.0  # 4 samples: shorter than one 6 Hz period at 30 fps (5)
    xy[15:40] = 2.0
    out = lowpass(xy, 30.0)
    assert np.isnan(out[5:9]).all() and np.allclose(out[15:40], 2.0)


# ---- segmentation ----------------------------------------------------------------------------
def test_segments_are_the_steady_parts_of_each_pass():
    clip, truth = synthetic_clip(passes=3)
    _, segs = walk_of(clip)
    assert len(segs) == 3
    for seg, (a, b) in zip(segs, truth.steady, strict=True):
        assert seg.start / clip.fps >= a - 0.2 and seg.end / clip.fps <= b + 0.2  # ramps excluded
        assert seg.seconds(clip.fps) >= 0.7 * (b - a)
    assert [s.direction for s in segs] == [1.0, -1.0, 1.0]


def test_turns_and_standing_are_excluded():
    clip, truth = synthetic_clip(passes=2, turn_secs=2.0)
    _, segs = walk_of(clip)
    turn = (truth.steady[0][1] + 0.8, truth.steady[1][0] - 0.8)  # between the passes
    for s in segs:
        assert s.end / clip.fps <= turn[0] or s.start / clip.fps >= turn[1]


def test_out_of_frame_landmarks_are_never_used():
    """Walks off both edges of a narrow frame. Landmarks outside the image are masked, so no heel
    strike can come from a heel outside the image and no knee value from a leg partly outside."""
    clip, _ = synthetic_clip(width=900, passes=2, pass_secs=5.0)
    walk, segs = walk_of(clip)
    assert segs and sum(len(v) for v in walk.heel_strikes.values()) >= 4
    lm = clip.landmarks
    for side, heel in (("L", 29), ("R", 30)):
        for f in walk.heel_strikes[side]:
            assert 0 <= lm.loc[f, f"lm{heel}_x"] <= 1 and 0 <= lm.loc[f, "lm23_x"] <= 1
    tracks = build_tracks(clip)
    outside = (lm["lm27_x"] < 0) | (lm["lm27_x"] > 1)
    assert outside.any() and np.isnan(tracks[("L", "ankle")][outside.to_numpy()]).all()


# ---- events and temporal metrics ---------------------------------------------------------------
@pytest.mark.parametrize("spm", [90, 110, 125])
def test_cadence_matches_ground_truth(spm):
    clip, _ = synthetic_clip(steps_per_min=spm, passes=4)
    r = analyse(clip)
    assert r.accepted, r.rejection
    assert r.metrics["cadence"]["value"] == pytest.approx(spm, abs=2)


def test_synthetic_110_steps_per_min_reads_110_plus_minus_2():
    """Phase 2 acceptance criterion."""
    r = analyse(synthetic_clip(steps_per_min=110)[0])
    assert r.metrics["cadence"]["value"] == pytest.approx(110, abs=2)


def test_heel_strikes_of_both_legs_are_found_near_the_truth():
    clip, truth = synthetic_clip()
    walk, _ = walk_of(clip)
    for side in "LR":
        det = np.array(walk.heel_strikes[side]) / clip.fps
        assert len(det) >= 4
        true = np.array(truth.heel_strikes[side])
        err = np.array([np.min(np.abs(true - d)) for d in det])
        assert (err <= 2 / clip.fps).all(), err  # within 2 frames (Zeni's method leads slightly)


LEG_PAIRS = ((25, 26), (27, 28), (29, 30), (31, 32))  # knee, ankle, heel, toe (L, R)


def flip_legs(clip, fraction, seed):
    """MediaPipe's left/right leg flips: for 1-2 frames the whole leg (knee, ankle, heel, toe) carries
    the other leg's label; the hips keep theirs. On LJMU (Topham et al. 2023, CC BY 4.0) the labels
    flipped between ~10-12% of consecutive frames in every accepted clip whose cadence read 136-158
    steps/min (P8: 116 on one task, 153 on the next). `fraction` of frames are flipped here."""
    rng, lm, flipped = np.random.default_rng(seed), clip.landmarks, set()
    while len(flipped) < fraction * clip.n_frames:
        start = int(rng.integers(0, clip.n_frames))
        flipped.update(range(start, min(clip.n_frames, start + int(rng.integers(1, 3)))))
    rows = sorted(flipped)
    for a, b in LEG_PAIRS:
        for k in ("x", "y", "z", "vis"):
            va, vb = lm.loc[rows, f"lm{a}_{k}"].to_numpy(), lm.loc[rows, f"lm{b}_{k}"].to_numpy()
            lm.loc[rows, f"lm{a}_{k}"], lm.loc[rows, f"lm{b}_{k}"] = vb, va
    return clip


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_brief_left_right_leg_flips_never_give_a_wrong_cadence(seed):
    r = analyse(flip_legs(synthetic_clip(steps_per_min=110)[0], 0.10, seed))
    if r.accepted:  # rejecting the clip is allowed; a wrong number is not
        assert r.metrics["cadence"]["value"] == pytest.approx(110, abs=2)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_heel_strikes_are_found_on_the_right_foot_despite_leg_flips(seed):
    clip, truth = synthetic_clip()
    walk, _ = walk_of(flip_legs(clip, 0.10, seed))
    for side in "LR":
        det = np.array(walk.heel_strikes[side]) / clip.fps
        assert len(det) >= 4, side
        err = np.array([np.min(np.abs(np.array(truth.heel_strikes[side]) - d)) for d in det])
        assert (err <= 2 / clip.fps).all(), (side, err)


def test_step_and_stride_times():
    r = analyse(synthetic_clip(steps_per_min=100, passes=3, pass_secs=6.0, width=2000)[0])
    assert r.metrics["step_time"]["value"] == pytest.approx(0.6, abs=0.02)
    for leg in ("left", "right"):
        st = r.metrics["stride_time"][leg]
        assert st is not None and st["value"] == pytest.approx(1.2, abs=0.03) and st["unit"] == "s"


def test_per_stride_peak_knee_flexion_matches_the_pixels():
    clip, _ = synthetic_clip()
    walk, _ = walk_of(clip)
    for side in "LR":
        truth = knee_flexion_truth(clip, side)
        hs = walk.heel_strikes[side]
        expected = [float(np.max(truth[a : b + 1])) for a, b in zip(hs, hs[1:], strict=False) if b - a < 60]
        assert walk.knee_peak_flexion[side], side
        assert np.median(walk.knee_peak_flexion[side]) == pytest.approx(np.median(expected), abs=1.0)


# ---- calibration ---------------------------------------------------------------------------------
def floor_calibration(truth, metres=4.0, x0=100.0):
    px = metres / 0.9 * 200  # the synthetic leg is 200 px = 0.9 m
    return Calibration(x0, truth.floor_y, x0 + px, truth.floor_y, metres)


def test_step_length_and_speed_only_with_calibration():
    clip, truth = synthetic_clip()
    plain = analyse(clip)
    assert "step_length" not in plain.metrics and "walking_speed" not in plain.metrics
    cal = analyse(clip, floor_calibration(truth))
    assert cal.metrics["step_length"]["value"] == pytest.approx(truth.step_length_m, rel=0.02)
    assert cal.metrics["step_length"]["unit"] == "m"
    assert cal.metrics["walking_speed"]["value"] == pytest.approx(truth.speed_m_s, rel=0.02)
    assert cal.metrics["walking_speed"]["unit"] == "m/s"


@pytest.mark.parametrize(
    "cal",
    [
        Calibration(10, 10, 50, 10, 1.0),  # 40 px apart
        Calibration(-5, 10, 500, 10, 2.0),  # outside the frame
        Calibration(10, 10, 500, 10, 0.05),  # implausible distance
    ],
)
def test_bad_calibration_is_refused_with_a_reason(cal):
    clip, _ = synthetic_clip()
    with pytest.raises(CalibrationError) as e:
        analyse(clip, cal)
    assert str(e.value)


# ---- quality gate --------------------------------------------------------------------------------
GATE_CASES = {
    "too_short": {"passes": 1, "pass_secs": 2.5},
    "low_frame_rate": {"fps": 15},
    "multiple_people": {"people": 2},
    "wrong_orientation": {"rotate90": True},
    "feet_not_visible": {"feet_visibility": 0.2},
    "not_side_view": {"yaw_deg": 40},
    "too_little_walking": {"passes": 1, "pass_secs": 3.4},
    "view_unconfirmed": {"step_ratio": 0.0},  # stepping on the spot: never walks across the frame
}


@pytest.mark.parametrize("code", GATE_CASES)
def test_quality_gate_rejects_with_a_specific_reason(code):
    r = analyse(synthetic_clip(**GATE_CASES[code])[0])
    assert r.status == "rejected" and r.rejection is not None
    assert r.rejection.code == code
    assert len(r.rejection.message) > 40
    assert r.metrics == {}  # no numbers for a rejected clip


def test_frontal_walk_is_rejected_as_not_side_view():
    assert analyse(synthetic_clip(yaw_deg=90)[0]).rejection.code == "not_side_view"


def test_no_person_is_rejected():
    clip, _ = synthetic_clip()
    clip.landmarks.loc[:, [c for c in clip.landmarks if c.startswith("lm")]] = np.nan
    assert analyse(clip).rejection.code == "no_person"


def test_slightly_oblique_side_view_is_accepted():
    assert analyse(synthetic_clip(yaw_deg=15)[0]).accepted


# A phone 3.5 m from the walking line (the capture tip says 3-4 m), seen as a pinhole camera.
PHONE_PX = 3.5 / M_PER_PX


def rolled(clip, deg):
    """The same scene filmed with the phone rolled by `deg`: landmarks rotated about the frame centre."""
    lm, a, w, h = clip.landmarks, np.radians(deg), clip.width, clip.height
    for i in range(33):
        x, y = lm[f"lm{i}_x"] * w - w / 2, lm[f"lm{i}_y"] * h - h / 2
        lm[f"lm{i}_x"] = (x * np.cos(a) - y * np.sin(a) + w / 2) / w
        lm[f"lm{i}_y"] = (x * np.sin(a) + y * np.cos(a) + h / 2) / h
    return clip


@pytest.mark.parametrize("yaw", [18, 22])
def test_oblique_walk_seen_in_perspective_is_rejected_as_not_side_view(yaw):
    """LJMU's 45 deg clips passed the shoulder-width rule 41% of the time; with perspective the
    walker's ankle and shoulder paths converge, which a side-on camera never shows."""
    r = analyse(synthetic_clip(yaw_deg=yaw, camera_distance=PHONE_PX)[0])
    assert r.quality["view_ratio"] <= quality.MAX_VIEW_RATIO  # the shoulder rule alone lets it through
    assert r.rejection is not None and r.rejection.code == "not_side_view"


@pytest.mark.parametrize("yaw", [0, 10])
def test_near_side_view_seen_in_perspective_is_accepted(yaw):
    r = analyse(synthetic_clip(yaw_deg=yaw, camera_distance=PHONE_PX)[0])
    assert r.accepted, r.rejection
    assert r.quality["path_convergence_deg"] < quality.MAX_PATH_CONVERGENCE


@pytest.mark.parametrize("deg", [-5, 5])
def test_side_view_decision_is_unaffected_by_camera_roll(deg):
    side = analyse(rolled(synthetic_clip(camera_distance=PHONE_PX)[0], deg))
    assert side.accepted, side.rejection
    oblique = analyse(rolled(synthetic_clip(yaw_deg=22, camera_distance=PHONE_PX)[0], deg))
    assert oblique.rejection is not None and oblique.rejection.code == "not_side_view"


def test_view_unconfirmed_message_asks_for_a_walk_across_the_frame():
    r = analyse(synthetic_clip(**GATE_CASES["view_unconfirmed"])[0])
    assert "side-on" in r.rejection.message and "across the frame" in r.rejection.message
    assert r.quality["path_convergence_deg"] is None


# ---- result shape ------------------------------------------------------------------------------
def test_result_has_units_quality_and_versions():
    d = analyse(synthetic_clip()[0]).to_dict()
    assert d["pipeline_version"] == "2.0.0" and d["status"] == "accepted" and d["rejection"] is None
    assert d["model"]["name"] == "pose_landmarker_full" and len(d["model"]["sha256"]) == 64
    for name, m in d["metrics"].items():
        for item in [m] if "unit" in m else list(m.values()):
            assert item is None or item["unit"], name
    q = d["quality"]
    for key in (
        "fps",
        "frames_total",
        "frames_with_pose",
        "usable_frame_fraction",
        "steps_detected",
        "strides",
        "path_convergence_deg",
    ):
        assert key in q
    assert 0 < q["usable_frame_fraction"] <= 1
    assert not any(isinstance(v, float) and math.isnan(v) for v in q.values())


def test_cadence_is_immune_to_a_constant_timing_offset_on_one_leg():
    """Heel-strike timing errors can differ between the near and far leg (or after a knee change).
    A constant offset d on one leg makes L->R steps t+d and R->L steps t-d; when a pass holds more of
    one kind, a plain mean is biased. Averaging the two alternations cancels d exactly."""
    from gaitcore.gait import Walk

    w = Walk(fps=30.0, step_times=[0.6, 0.5, 0.6, 0.5, 0.6], step_ends=["R", "L", "R", "L", "R"])
    assert w.cadence == pytest.approx(60 / 0.55)
    assert w.mean_step_time == pytest.approx(0.55)


def test_only_kept_metrics_are_returned():
    """Plan V3: hip sagittal excursion is CONDITIONAL (must pass the Phase 3 accuracy check)."""
    metrics = analyse(synthetic_clip()[0]).to_dict()["metrics"]
    assert set(metrics) == {"cadence", "step_time", "stride_time", "peak_knee_flexion"}
