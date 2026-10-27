"""Measurement core v2 on synthetic ground truth (Plan V3 Phase 2, ADR-006).

All inputs are synthetic (tests/synthetic.py); results are synthetic-ground-truth checks, not
accuracy against real people (that is Phase 3).
"""

import math

import numpy as np
import pytest
from synthetic import LEG, M_PER_PX, knee_flexion_truth, synthetic_clip

from gaitcore import quality
from gaitcore.calibration import Calibration, CalibrationError
from gaitcore.clip import Clip
from gaitcore.gait import leg_length, measure_passes, measure_walk
from gaitcore.pipeline import UnsupportedTest, analyse
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


@pytest.mark.parametrize("fps", [25, 60])
def test_cadence_is_right_at_other_frame_rates(fps):
    """Event times are found to a fraction of a frame, so a step time that isn't a whole number of
    frames (110 steps/min = 13.6 frames at 25 fps) doesn't round the cadence."""
    r = analyse(synthetic_clip(steps_per_min=110, fps=fps)[0])
    assert r.accepted, r.rejection
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


def test_cadence_and_step_time_do_not_depend_on_the_left_right_labels():
    """Cadence and step time come from the distance between the heels, |x_L - x_R|, which swapping
    the leg labels can't change: any amount of label flipping gives exactly the same values."""
    base = analyse(synthetic_clip(steps_per_min=110)[0])
    assert base.accepted
    for fraction, seed in ((0.1, 1), (0.3, 2), (0.5, 3)):
        r = analyse(flip_legs(synthetic_clip(steps_per_min=110)[0], fraction, seed))
        assert r.accepted, (fraction, r.rejection)
        assert r.metrics["cadence"] == base.metrics["cadence"], fraction
        assert r.metrics["step_time"] == base.metrics["step_time"], fraction


# A continuity correction (two-state Viterbi per pass, _audit/sandbox/ljmu_cache/scripts/legfix.py)
# passes this on the synthetic walker, but on LJMU (Topham et al. 2023, CC BY 4.0; 77 accepted clips,
# 2026-10-26) it left per-leg stride time as wrong as before (MAE 241 -> 246 ms vs 2x the reference
# step time): there the labels mostly follow the legs' position, so 37/110 legs read one step as a
# stride. Not shipped; stride time stays withheld.
LEG_FLIPS_UNFIXED = pytest.mark.xfail(
    strict=True, reason="per-foot heel strikes follow the leg labels; no label correction is shipped"
)


@pytest.mark.parametrize("seed", [pytest.param(s, marks=LEG_FLIPS_UNFIXED) for s in (0, 1, 2, 3)])
def test_heel_strikes_are_found_on_the_right_foot_despite_leg_flips(seed):
    clip, truth = synthetic_clip()
    walk, _ = walk_of(flip_legs(clip, 0.10, seed))
    for side in "LR":
        det = np.array(walk.heel_strikes[side]) / clip.fps
        assert len(det) >= 4, side
        err = np.array([np.min(np.abs(np.array(truth.heel_strikes[side]) - d)) for d in det])
        assert (err <= 2 / clip.fps).all(), (side, err)


def test_step_and_stride_times():
    """Stride time is still computed (for the Phase 3 check) but not returned: brief left/right
    label flips can make it read up to 26% short without tripping the per-leg check."""
    clip = synthetic_clip(steps_per_min=100, passes=3, pass_secs=6.0, width=2000)[0]
    r = analyse(clip)
    assert r.metrics["step_time"]["value"] == pytest.approx(0.6, abs=0.02)
    assert "stride_time" not in r.metrics
    walk, _ = walk_of(clip)
    for side in "LR":
        assert len(walk.stride_times[side]) >= 3
        assert np.mean(walk.stride_times[side]) == pytest.approx(1.2, abs=0.03)


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


# ---- real-world recordings ---------------------------------------------------------------------
# On three phone clips the hip midpoint sped up and slowed down by ~20% of the walking speed once per
# step and ~8% once per stride (up to 27% / 12% in one pass). At a slow cadence a fixed half-second
# average leaves that ripple in and chops every pass into pieces too short to hold a step.
REAL_SURGE = (0.27, 0.12)


@pytest.mark.parametrize("spm", [80, 85])
def test_a_slow_walker_with_a_real_hip_ripple_is_measured(spm):
    clip, truth = synthetic_clip(
        steps_per_min=spm, pass_secs=6.0, pelvis_surge=REAL_SURGE, noise_px=1.0, seed=1
    )
    r = analyse(clip)
    assert r.accepted, r.rejection
    assert r.metrics["cadence"]["value"] == pytest.approx(truth.cadence, abs=1)
    assert r.quality["steadiness_window_s"] == pytest.approx(60 / spm, abs=0.05)


def test_the_steadiness_window_is_one_step_kept_within_half_a_second_and_a_second():
    assert analyse(synthetic_clip(steps_per_min=130)[0]).quality["steadiness_window_s"] == 0.5
    slow = analyse(synthetic_clip(steps_per_min=50, pass_secs=8.0, width=2000)[0])
    assert slow.quality["steadiness_window_s"] == 1.0


def with_second_person(clip, start_s, end_s):
    """Someone else walks into view from start_s to end_s (the pose model sees two people)."""
    lm = clip.landmarks.copy()
    lm.loc[int(start_s * clip.fps) : int(end_s * clip.fps) - 1, "n_poses"] = 2
    return Clip(lm, clip.fps, clip.width, clip.height)


def with_feet_cut_off(clip, start_s, end_s):
    """From start_s to end_s the feet are below the bottom edge of the frame."""
    lm = clip.landmarks.copy()
    rows = slice(int(start_s * clip.fps), int(end_s * clip.fps) - 1)
    for i in range(27, 33):
        lm.loc[rows, f"lm{i}_y"] = 1.05
    return Clip(lm, clip.fps, clip.width, clip.height)


# Three 8 s passes with 1.5 s turns: pass k runs from 9.5k to 9.5k + 8 s.
THREE_PASSES = {"passes": 3, "pass_secs": 8.0}


def test_a_second_person_in_part_of_the_video_drops_only_that_part():
    clip, truth = synthetic_clip(**THREE_PASSES)
    r = analyse(with_second_person(clip, 0, 9.5))  # the whole first pass: 35% of the video
    assert r.accepted, r.rejection
    assert r.quality["passes"] == 2
    assert r.quality["second_person_s"] == pytest.approx(9.5, abs=0.1)
    assert r.metrics["cadence"]["value"] == pytest.approx(truth.cadence, abs=1)


def test_feet_cut_off_in_part_of_the_video_drop_only_that_part():
    clip, truth = synthetic_clip(**THREE_PASSES)
    r = analyse(with_feet_cut_off(clip, 0, 19.0))  # the first two passes: 70% of the video
    assert r.accepted, r.rejection
    assert r.quality["feet_visible_fraction"] < 0.5  # used to reject the whole video
    assert r.quality["passes"] == 1
    assert r.quality["heels_hidden_s"] == pytest.approx(19.0, abs=0.5)
    assert r.metrics["cadence"]["value"] == pytest.approx(truth.cadence, abs=1)


def test_a_second_person_and_cut_off_feet_together_drop_only_those_parts():
    clip, truth = synthetic_clip(**THREE_PASSES)
    r = analyse(with_feet_cut_off(with_second_person(clip, 0, 9.5), 9.5, 19.0))
    assert r.accepted, r.rejection
    assert r.quality["passes"] == 1
    assert r.metrics["cadence"]["value"] == pytest.approx(truth.cadence, abs=1)


def test_feet_hidden_for_less_than_a_step_are_kept():
    clip, _ = synthetic_clip(**THREE_PASSES)
    clean = analyse(clip)
    r = analyse(with_feet_cut_off(clip, 3.0, 3.3))  # 0.3 s: shorter than one step
    assert r.quality["heels_hidden_s"] == 0
    assert r.quality["steady_walking_s"] == clean.quality["steady_walking_s"]


def test_the_rejection_names_a_second_person_who_left_too_little_walking():
    clip, _ = synthetic_clip(passes=3, pass_secs=4.0)
    r = analyse(with_second_person(clip, 0, 11.0))  # two of three short passes
    assert r.rejection is not None and r.rejection.code == "multiple_people"
    assert "11 s" in r.rejection.message and "only the person who is walking" in r.rejection.message


def test_the_rejection_names_feet_out_of_view_that_left_too_little_walking():
    clip, _ = synthetic_clip(passes=3, pass_secs=4.0)
    r = analyse(with_feet_cut_off(clip, 0, 11.0))
    assert r.rejection is not None and r.rejection.code == "feet_not_visible"
    assert "11 s" in r.rejection.message and "both feet" in r.rejection.message


def test_too_little_walking_with_nothing_dropped_still_says_so():
    r = analyse(synthetic_clip(**GATE_CASES["too_little_walking"])[0])
    assert r.rejection.code == "too_little_walking"
    assert r.quality["second_person_s"] == 0 and r.quality["heels_hidden_s"] == 0


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
        "step_time_cv",
        "path_convergence_deg",
    ):
        assert key in q
    assert 0 < q["usable_frame_fraction"] <= 1
    assert not any(isinstance(v, float) and math.isnan(v) for v in q.values())


def test_cadence_is_immune_to_a_constant_timing_offset_on_one_leg():
    """Event timing errors can differ between the near and far leg (or after a knee change). The
    step events alternate between the feet, so a constant offset d on one foot's events makes
    alternate steps t+d and t-d; when a run holds an odd number of steps, a plain mean is biased.
    Averaging the two alternations of each run cancels d exactly."""
    from gaitcore.gait import Walk

    w = Walk(fps=30.0, contact_runs=[[0.0, 0.6, 1.1, 1.7, 2.2, 2.8]])  # steps 0.6 0.5 0.6 0.5 0.6
    assert w.cadence == pytest.approx(60 / 0.55)
    assert w.mean_step_time == pytest.approx(0.55)
    w.contact_runs.append([10.0, 10.5, 11.1, 11.6])  # a second pass: 0.5 0.6 0.5
    assert w.mean_step_time == pytest.approx(0.55)
    assert w.step_count == 8


def test_per_leg_values_are_hidden_when_left_and_right_steps_are_too_variable():
    """Knee flexion per leg needs the left/right labels. When the steps between
    labelled heel strikes vary by more than 20% (coefficient of variation), the labels are not
    trusted: per-leg values are withheld with a note, and cadence and step time (label-free) stay."""
    from gaitcore.gait import Walk
    from gaitcore.result import LEGS_NOT_TOLD_APART, metrics_from_walk, notes_from_walk

    def walk(step_times):
        return Walk(
            fps=30.0,
            contact_runs=[[0.0, 0.55, 1.1, 1.65, 2.2, 2.75, 3.3]],
            step_times=step_times,
            stride_times={"L": [1.1, 1.1, 1.1], "R": [1.1, 1.1, 1.1]},
            knee_peak_flexion={"L": [60.0, 61.0, 59.0], "R": [58.0, 60.0, 59.0]},
        )

    steady = walk([0.55, 0.56, 0.54, 0.55, 0.55, 0.56])  # CV 0.01
    m = metrics_from_walk(steady)
    assert m["peak_knee_flexion"]["left"]["value"] == pytest.approx(60.0) and m["peak_knee_flexion"]["right"]
    assert notes_from_walk(steady) == []

    erratic = walk([0.55, 0.30, 0.80, 0.25, 0.85, 0.55])  # CV 0.44: labels swapping
    m = metrics_from_walk(erratic)
    assert m["peak_knee_flexion"] == {"left": None, "right": None}
    assert m["cadence"]["value"] == pytest.approx(60 / 0.55, abs=0.1)
    assert notes_from_walk(erratic) == [LEGS_NOT_TOLD_APART]
    assert "left and right legs" in LEGS_NOT_TOLD_APART.lower()
    assert "stride" not in LEGS_NOT_TOLD_APART.lower()  # stride time isn't shown at all


def test_per_leg_values_are_hidden_when_a_legs_strides_are_not_two_steps_long():
    """On LJMU the labels often follow the legs' position in the image, and a 'stride' of one label is
    then one step. A leg's median stride time must be within MAX_STRIDE_MISMATCH of twice the
    label-free step time, or per-leg values are withheld."""
    from gaitcore.gait import Walk
    from gaitcore.result import LEGS_NOT_TOLD_APART, metrics_from_walk, notes_from_walk

    def walk(left_strides):
        return Walk(
            fps=30.0,
            contact_runs=[[0.0, 0.55, 1.1, 1.65, 2.2, 2.75, 3.3]],
            step_times=[0.55, 0.56, 0.54, 0.55, 0.55, 0.56],
            stride_times={"L": left_strides, "R": [1.1, 1.1, 1.1]},
            knee_peak_flexion={"L": [60.0, 61.0, 59.0], "R": [58.0, 60.0, 59.0]},
        )

    assert metrics_from_walk(walk([1.05, 1.1, 1.15]))["peak_knee_flexion"]["left"] is not None
    halved = walk([0.55, 0.55, 1.1])
    assert metrics_from_walk(halved)["peak_knee_flexion"] == {"left": None, "right": None}
    assert notes_from_walk(halved) == [LEGS_NOT_TOLD_APART]


@pytest.mark.parametrize("seed", range(8))
def test_knee_values_under_brief_leg_flips_are_hidden_or_right(seed):
    """10% of frames flipped: the stride check hides the per-leg values whenever a leg's strides come
    out short. (At 5%, 2 of 8 seeds still show a left knee 4-6 deg low with normal strides: Phase 8.)"""
    base = analyse(synthetic_clip()[0]).metrics["peak_knee_flexion"]
    knee = analyse(flip_legs(synthetic_clip()[0], 0.10, seed)).metrics["peak_knee_flexion"]
    for side in ("left", "right"):
        if knee[side] is not None:
            assert knee[side]["value"] == pytest.approx(base[side]["value"], abs=1.0), side


def test_result_carries_user_facing_notes():
    assert analyse(synthetic_clip()[0]).to_dict()["notes"] == []


def collapse_legs(clip):
    """MediaPipe sometimes puts both legs on the same one: the right leg's points copy the left's."""
    lm = clip.landmarks
    for a, b in LEG_PAIRS:
        for k in ("x", "y", "z", "vis"):
            lm[f"lm{b}_{k}"] = lm[f"lm{a}_{k}"]
    return clip


def test_enough_walking_but_too_few_steps_is_reported_as_legs_not_tracked():
    """>= 4 s of steady walking holds at least 6 steps at any normal cadence (6 x 0.67 s at
    90 steps/min), so finding fewer means the legs weren't followed, not that the walk was short."""
    r = analyse(collapse_legs(synthetic_clip(passes=2)[0]))
    assert r.quality["steady_walking_s"] >= 4.0
    assert r.status == "rejected" and r.rejection.code == "legs_not_tracked"
    assert "legs" in r.rejection.message and len(r.rejection.message) > 40
    assert r.metrics == {}
    short = analyse(collapse_legs(synthetic_clip(passes=1, pass_secs=4.0)[0]))  # 2.4 s steady
    assert short.rejection.code == "too_little_walking"


def spurious_heel_bumps(clip, truth, amp=0.8, every=2):
    """A short forward jump of the left heel point between steps, as a mis-tracked heel gives:
    the heel separation gets an extra peak there."""
    lm = clip.landmarks
    t = np.arange(len(lm)) / clip.fps
    hs = np.sort(truth.heel_strikes["L"] + truth.heel_strikes["R"])
    x = lm["lm29_x"].to_numpy(dtype=float)
    for mid in ((hs[:-1] + hs[1:]) / 2)[::every]:
        x = x + amp * LEG / clip.width * np.exp(-0.5 * ((t - mid) / 0.08) ** 2)
    lm["lm29_x"] = x
    return clip


def test_irregular_label_free_steps_are_rejected():
    """Spurious separation peaks between real steps make the label-free step times irregular; on
    held-out LJMU clips every cadence error over 6 steps/min had a step-time CV above 0.15."""
    assert analyse(synthetic_clip()[0]).status == "accepted"
    r = analyse(spurious_heel_bumps(*synthetic_clip()))
    assert r.quality["step_time_cv"] > quality.MAX_STEP_TIME_CV
    assert r.status == "rejected" and r.rejection.code == "irregular_steps"
    assert "steadily" in r.rejection.message and r.metrics == {}


def test_step_time_irregularity_threshold():
    assert quality.MAX_STEP_TIME_CV == 0.15
    assert quality.regular_steps([0.55] * 8) is None
    assert quality.regular_steps([0.5, 0.6] * 4) is None  # CV 0.10
    r = quality.regular_steps([0.45, 0.65] * 4)  # CV 0.19
    assert r is not None and r.code == "irregular_steps"
    assert quality.regular_steps([0.55]) is None  # one step: no spread to judge


def test_only_kept_metrics_are_returned():
    """Plan V3: hip sagittal excursion is CONDITIONAL (must pass the Phase 3 accuracy check). Stride
    time is withheld until Phase 3: brief left/right flips make it wrong without any warning."""
    metrics = analyse(synthetic_clip()[0]).to_dict()["metrics"]
    assert set(metrics) == {"cadence", "step_time", "peak_knee_flexion"}


# ---- passes, test types, treadmill (Phase 3) ---------------------------------------------------
def surge(clip, start_s, secs=0.6, px=60.0):
    """The walker speeds up briefly mid-pass: every landmark moves px further over secs."""
    t = np.arange(clip.n_frames) / clip.fps
    u = np.clip((t - start_s) / secs, 0, 1)
    shift = px * (1 - np.cos(np.pi * u)) / 2 / clip.width
    lm = clip.landmarks.copy()
    for c in lm:
        if c.endswith("_x"):
            lm[c] = lm[c] + shift
    return Clip(lm, clip.fps, clip.width, clip.height)


def on_treadmill(clip):
    """The same walker on a treadmill: the pelvis held still mid-frame, the feet carried back."""
    lm = clip.landmarks.copy()
    pelvis = (lm["lm23_x"] + lm["lm24_x"]) / 2
    for c in lm:
        if c.endswith("_x"):
            lm[c] = lm[c] - pelvis + 0.5
    return Clip(lm, clip.fps, clip.width, clip.height)


def test_each_steady_segment_knows_its_walk_across():
    _, segs = walk_of(synthetic_clip(passes=3)[0])
    assert [s.pass_index for s in segs] == [0, 1, 2]


def test_a_speed_change_mid_pass_splits_the_segment_not_the_pass():
    clip = surge(synthetic_clip(passes=2, pass_secs=6.0, width=2000)[0], 2.5)
    _, segs = walk_of(clip)
    assert len(segs) > 2  # the surge isn't steady walking
    assert sorted({s.pass_index for s in segs}) == [0, 1]
    assert analyse(clip).quality["passes"] == 2


def test_per_pass_walks_pool_to_the_whole_walk():
    clip, truth = synthetic_clip(passes=3, pass_secs=6.0, width=2000)
    tracks = build_tracks(clip)
    segs = steady_segments(clip, tracks, leg_length(tracks))
    passes = measure_passes(clip, segs, tracks=tracks)
    whole = measure_walk(clip, segs, tracks=tracks)
    assert len(passes) == 3
    for p in passes:
        assert p.step_count >= 6 and p.cadence == pytest.approx(truth.cadence, abs=2)
    for name in ("contact_runs", "step_times", "step_ends"):
        assert [x for p in passes for x in getattr(p, name)] == getattr(whole, name)
    for name in ("heel_strikes", "stride_times", "knee_peak_flexion", "hip_excursion"):
        for s in ("L", "R"):
            assert [x for p in passes for x in getattr(p, name)[s]] == getattr(whole, name)[s]


def test_result_names_its_test():
    assert analyse(synthetic_clip()[0]).to_dict()["test"] == "walk"
    assert analyse(synthetic_clip(fps=15)[0]).to_dict()["test"] == "walk"  # rejected ones too


def test_a_test_without_a_validated_analysis_is_refused():
    with pytest.raises(UnsupportedTest):
        analyse(synthetic_clip()[0], test="sit_to_stand")


def test_treadmill_walk_is_rejected_until_treadmill_mode_has_its_own_view_check():
    clip = on_treadmill(synthetic_clip(passes=1, pass_secs=12.0, ramp_secs=0.3)[0])
    assert analyse(clip).rejection.code == "view_unconfirmed"


def test_event_timing_works_for_a_walker_who_never_crosses_the_frame():
    """What treadmill mode can build on: steps are timed without the pelvis moving across the image."""
    clip, truth = synthetic_clip(passes=1, pass_secs=12.0, ramp_secs=0.3)
    walk = measure_walk(on_treadmill(clip))
    assert walk.step_count >= 15
    assert walk.cadence == pytest.approx(truth.cadence, abs=2)


def test_metrics_without_a_reference_check_are_marked_not_yet_validated():
    """No knee-angle reference without OpenCap (Phase 8); calibrated distances are checked on the
    synthetic walker only."""
    clip, truth = synthetic_clip()
    acc = analyse(clip, floor_calibration(truth)).to_dict()["accuracy"]
    for name in ("peak_knee_flexion", "step_length", "walking_speed"):
        assert acc[name]["status"] == "not_yet_validated", name
        assert "not yet validated" in acc[name]["note"].lower()
    assert analyse(synthetic_clip(fps=15)[0]).to_dict()["accuracy"] == {}  # rejected: no metrics


def test_each_pass_gets_its_own_cadence_and_the_spread_between_passes():
    clip, truth = synthetic_clip(passes=3, pass_secs=6.0, width=2000)
    d = analyse(clip).to_dict()
    assert [p["pass"] for p in d["passes"]] == [1, 2, 3]
    assert [p["direction"] for p in d["passes"]] == ["left_to_right", "right_to_left", "left_to_right"]
    for p in d["passes"]:
        assert p["steps"] >= quality.MIN_STEPS
        assert (
            p["cadence"]["value"] == pytest.approx(truth.cadence, abs=2)
            and p["cadence"]["unit"] == "steps/min"
        )
        assert (
            p["step_time"]["value"] == pytest.approx(60 / truth.cadence, abs=0.01)
            and p["step_time"]["unit"] == "s"
        )
    v = d["pass_variability"]
    assert v["passes"] == 3 and 0 <= v["cadence_sd"]["value"] < 2 and v["cadence_sd"]["unit"] == "steps/min"
    assert v["step_time_sd"]["unit"] == "s"


def test_passes_with_too_few_steps_get_no_values_of_their_own():
    """Each pass of the default walker holds 3 steps: the clip's cadence pools them, but no pass is
    timed alone (the same MIN_STEPS resolution bound as the whole clip)."""
    d = analyse(synthetic_clip()[0]).to_dict()
    assert d["status"] == "accepted" and d["passes"] == [] and d["pass_variability"] is None


def test_each_leg_gets_a_mean_knee_curve_over_the_stride():
    d = analyse(synthetic_clip()[0]).to_dict()
    curves = d["curves"]["knee_flexion"]
    assert curves["unit"] == "deg" and curves["points"] == 101
    for side in ("left", "right"):
        c = curves[side]
        assert len(c) == 101
        # Its peak is the average stride's peak: close to the median per-stride peak reported.
        assert max(c) == pytest.approx(d["metrics"]["peak_knee_flexion"][side]["value"], abs=3)


def test_no_knee_curve_when_per_leg_values_are_hidden():
    d = analyse(flip_legs(synthetic_clip()[0], 0.10, 1)).to_dict()  # strides come out short: hidden
    assert d["status"] == "accepted" and d["metrics"]["peak_knee_flexion"] == {"left": None, "right": None}
    assert d["curves"]["knee_flexion"]["left"] is None and d["curves"]["knee_flexion"]["right"] is None
    assert analyse(synthetic_clip(fps=15)[0]).to_dict()["curves"] == {}
