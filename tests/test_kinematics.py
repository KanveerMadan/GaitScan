"""Label-free knee and hip measures (Plan V3 Phase 11, owner decision B, 2026-11-14).

MediaPipe's left/right leg labels can't be trusted on LJMU (docs/validation/leg-labels.md), so each
stride's leg is found from foot motion: the leg that strikes at a step event is the one whose heel is
in front; while it stands, its heel stays on its footprint; after the other foot lands, it's the leg
away from the new footprint. The values are for both legs pooled. Every answer here comes from the
synthetic walker's own pixels and known heel strikes, not from the code under test."""

import numpy as np
import pytest
from synthetic import STANCE, synthetic_clip
from test_measurement import LEG_PAIRS, flip_legs

from gaitcore.gait import leg_length
from gaitcore.kinematics import CURVE_POINTS, measure_kinematics
from gaitcore.pipeline import analyse, walking
from gaitcore.signals import build_tracks, lowpass


def kinematics(clip):
    tracks = build_tracks(clip)
    segs = walking(clip, tracks, leg_length(tracks)).segments
    return measure_kinematics(clip, segs, tracks)


def raw(clip, i):
    lm = clip.landmarks
    return np.c_[lm[f"lm{i}_x"] * clip.width, lm[f"lm{i}_y"] * clip.height]


def px(clip, i):
    """Landmark i in pixels with the pipeline's 6 Hz low-pass (signals.lowpass): the measurement is
    defined on filtered tracks, and the synthetic legs have kinks at the events that real legs don't."""
    return lowpass(raw(clip, i), clip.fps)


def direction(clip):
    vx = np.gradient(raw(clip, 23)[:, 0])
    d = np.sign(vx)
    for i in range(1, len(d)):  # standing still: keep the last direction
        if d[i] == 0:
            d[i] = d[i - 1]
    return np.where(d == 0, 1.0, d)


def signed(a, b, d):
    """Angle of vector b against vector a, + when b points further along the walking direction d."""
    ang = np.degrees(np.arctan2(b[:, 1], b[:, 0]) - np.arctan2(a[:, 1], a[:, 0]))
    ang = (ang + 180) % 360 - 180
    return ang * -d  # image y points down: a clockwise turn towards +x reads negative


IDX = {"L": (23, 25, 27, 29, 31), "R": (24, 26, 28, 30, 32)}


def truth_angles(clip):
    """Per leg, from the pixels: knee flexion (180 - hip-knee-ankle angle); hip flexion (thigh against
    the downward trunk line, + = knee ahead); ankle (shank against foot, - 90, + = dorsiflexion)."""
    d = direction(clip)
    pelvis = (px(clip, 23) + px(clip, 24)) / 2
    shoulders = (px(clip, 11) + px(clip, 12)) / 2
    out = {}
    for side, (_, k, a, h, t) in IDX.items():
        knee, ankle, heel, toe = px(clip, k), px(clip, a), px(clip, h), px(clip, t)
        u, w = pelvis - knee, ankle - knee
        cos = (u * w).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(w, axis=1)
        knee_flex = 180 - np.degrees(np.arccos(np.clip(cos, -1, 1)))
        hip_flex = signed(pelvis - shoulders, knee - pelvis, d)
        shank, foot = ankle - knee, toe - heel
        ang = np.degrees(
            np.arccos(
                np.clip(
                    (shank * foot).sum(1) / np.linalg.norm(shank, axis=1) / np.linalg.norm(foot, axis=1),
                    -1,
                    1,
                )
            )
        )
        out[side] = {"knee": knee_flex, "hip": hip_flex, "ankle": 90 - ang}
    return out


def truth_strides(clip, truth):
    """(side, heel strike frame, toe-off frame, next heel strike frame) for strides inside steady walking."""
    T = 2 * 60.0 / truth.cadence
    out = []
    for side, hs in truth.heel_strikes.items():
        for a, b in zip(hs, hs[1:], strict=False):
            if any(s0 <= a and b <= s1 for s0, s1 in truth.steady):
                out.append(
                    (side, round(a * clip.fps), round((a + STANCE * T) * clip.fps), round(b * clip.fps))
                )
    return out


def truth_events(clip, truth):
    ang = truth_angles(clip)
    ev = {
        k: [] for k in ("knee_ic", "knee_peak_swing", "knee_rom", "hip_peak_ext", "hip_peak_flex", "hip_rom")
    }
    for side, hs, to, nxt in truth_strides(clip, truth):
        knee, hip = ang[side]["knee"][hs : nxt + 1], ang[side]["hip"][hs : nxt + 1]
        ev["knee_ic"].append(knee[0])
        # The strike is timed to +-1 frame (33 ms at 30 fps; the stance test checks timing): the knee
        # at contact may be anywhere in that span.
        ev.setdefault("knee_ic_lo", []).append(ang[side]["knee"][hs - 1 : hs + 2].min())
        ev.setdefault("knee_ic_hi", []).append(ang[side]["knee"][hs - 1 : hs + 2].max())
        ev["knee_peak_swing"].append(ang[side]["knee"][to : nxt + 1].max())
        ev["knee_rom"].append(np.ptp(knee))
        ev["hip_peak_ext"].append(ang[side]["hip"][hs : to + 1].min())
        ev["hip_peak_flex"].append(hip.max())
        ev["hip_rom"].append(np.ptp(hip))
    return {k: float(np.median(v)) for k, v in ev.items()}


def position_labels(clip):
    """LJMU's failure mode: the labels follow position, "L" always being the leg in front (hips kept)."""
    d = direction(clip)
    heel_l, heel_r = raw(clip, 29)[:, 0], raw(clip, 30)[:, 0]
    rows = np.flatnonzero((heel_l - heel_r) * d < 0)
    lm = clip.landmarks
    for a, b in LEG_PAIRS:
        for k in ("x", "y", "z", "vis"):
            va, vb = lm.loc[rows, f"lm{a}_{k}"].to_numpy(), lm.loc[rows, f"lm{b}_{k}"].to_numpy()
            lm.loc[rows, f"lm{a}_{k}"], lm.loc[rows, f"lm{b}_{k}"] = vb, va
    return clip


def test_toe_off_stance_and_double_support_match_the_walker():
    clip, truth = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    k = kinematics(clip)
    assert len(k.strides) >= 10
    assert k.summary()["stance_pct"]["value"] == pytest.approx(100 * STANCE, abs=2.0)
    assert k.summary()["double_support_pct"]["value"] == pytest.approx(100 * 2 * (STANCE - 0.5), abs=3.0)
    true_to = sorted(to for _, _, to, _ in truth_strides(clip, truth))
    found = [s.toe_off for s in k.strides if s.toe_off is not None]
    assert all(min(abs(f - t) for t in true_to) <= 2 for f in found)


def test_knee_and_hip_key_events_and_ranges_match_the_pixels():
    clip, truth = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    got = kinematics(clip).summary()
    want = truth_events(clip, truth)
    for name in ("knee_peak_swing", "knee_rom", "hip_peak_ext", "hip_peak_flex", "hip_rom"):
        assert got[name]["value"] == pytest.approx(want[name], abs=3.0), name
    assert want["knee_ic_lo"] - 1.5 <= got["knee_ic"]["value"] <= want["knee_ic_hi"] + 1.5
    assert 40 <= got["knee_peak_swing"]["value"] <= 75  # the walker bends its knees like a person


@pytest.mark.parametrize("scramble", ["brief_flips", "labels_follow_position"])
def test_left_right_label_errors_dont_change_the_values(scramble):
    clean = kinematics(
        synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0]
    ).summary()
    clip, _ = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    clip = flip_legs(clip, 0.10, 3) if scramble == "brief_flips" else position_labels(clip)
    got = kinematics(clip).summary()
    for name in ("knee_peak_swing", "knee_rom", "hip_peak_ext", "hip_peak_flex", "hip_rom", "stance_pct"):
        assert got[name]["value"] == pytest.approx(clean[name]["value"], abs=3.0), (scramble, name)
        assert got[name]["n"] >= 0.7 * clean[name]["n"], (scramble, name)


def test_the_mean_curves_follow_the_true_curves():
    clip, truth = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    curves = kinematics(clip).curves()
    ang = truth_angles(clip)
    for joint in ("knee", "hip", "ankle"):
        mean, sd = np.asarray(curves[joint]["mean"]), np.asarray(curves[joint]["sd"])
        assert len(mean) == len(sd) == CURVE_POINTS == 101
        true = [
            np.interp(
                np.linspace(hs, nxt, CURVE_POINTS), np.arange(hs, nxt + 1), ang[side][joint][hs : nxt + 1]
            )
            for side, hs, _, nxt in truth_strides(clip, truth)
        ]
        # Shape, not timing (the events' timing is checked above): the best match within +-2% of the cycle.
        want = np.mean(true, axis=0)
        rms = min(float(np.sqrt(np.mean((np.roll(mean, k)[3:-3] - want[3:-3]) ** 2))) for k in range(-2, 3))
        assert rms < 3.0, (joint, rms)


def test_both_walking_directions_read_the_same():
    clip, _ = synthetic_clip(passes=4, pass_secs=6.0, width=2000, swing_profile="brisk")
    k = kinematics(clip)
    by_dir = {d: [s.knee_peak_swing for s in k.strides if s.direction == d] for d in (1.0, -1.0)}
    assert len(by_dir[1.0]) >= 3 and len(by_dir[-1.0]) >= 3
    assert np.median(by_dir[1.0]) == pytest.approx(np.median(by_dir[-1.0]), abs=1.5)


def test_trunk_lean_pelvis_oscillation_and_arm_swing():
    clip, truth = synthetic_clip(
        passes=3, pass_secs=6.0, width=2000, swing_profile="brisk", trunk_lean_deg=8.0, arm_swing_deg=40.0
    )
    s = kinematics(clip).summary()
    assert s["trunk_lean_deg"]["value"] == pytest.approx(8.0, abs=0.5)
    assert s["arm_swing_deg"]["value"] == pytest.approx(40.0, abs=3.0)
    pelvis_y = ((px(clip, 23) + px(clip, 24)) / 2)[:, 1]  # filtered, like every truth here
    ranges = [np.ptp(pelvis_y[hs : nxt + 1]) for _, hs, _, nxt in truth_strides(clip, truth)]
    assert s["pelvis_oscillation"]["value"] == pytest.approx(
        np.median(ranges) / 200.0, abs=0.005
    )  # LEG = 200 px


def test_without_wrists_there_is_no_arm_swing():
    s = kinematics(synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0]).summary()
    assert s["arm_swing_deg"] is None


def test_a_knee_hidden_too_long_leaves_its_strides_knee_values_out_not_guessed():
    clip, _ = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    full = kinematics(clip).summary()
    hidden = np.arange(clip.n_frames) % 100 < 4  # both knees hidden 4 frames in every 100: not filled
    clip.landmarks.loc[hidden, ["lm25_vis", "lm26_vis"]] = 0.1
    gappy = kinematics(clip).summary()
    assert 0 < gappy["knee_rom"]["n"] < full["knee_rom"]["n"]
    assert gappy["knee_rom"]["value"] == pytest.approx(full["knee_rom"]["value"], abs=3.0)
    assert gappy["stance_pct"]["n"] == full["stance_pct"]["n"]  # the feet were seen: timing is kept


def test_a_knee_hidden_for_a_frame_or_two_is_bridged():
    clip, _ = synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")
    full = kinematics(clip).summary()
    hidden = np.arange(clip.n_frames) % 20 < 2  # 2 frames in every 20: short enough to interpolate
    clip.landmarks.loc[hidden, ["lm25_vis", "lm26_vis"]] = 0.1
    bridged = kinematics(clip).summary()
    # Bridged everywhere but at a run's first or last frame, which has nothing on one side to bridge from.
    assert bridged["knee_rom"]["n"] >= full["knee_rom"]["n"] - 1
    assert bridged["knee_peak_swing"]["value"] == pytest.approx(full["knee_peak_swing"]["value"], abs=3.0)


def test_fewer_than_three_strides_give_no_values():
    clip, _ = synthetic_clip(passes=1, pass_secs=2.6, ramp_secs=0.3, swing_profile="brisk")
    s = kinematics(clip).summary()
    assert s["knee_rom"] is None and s["hip_rom"] is None and s["stance_pct"] is None


def test_the_analysis_carries_the_kinematics_but_its_result_dict_is_unchanged():
    r = analyse(synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0])
    assert r.accepted and r.kinematics is not None and r.kinematics.summary()["knee_rom"] is not None
    assert "kinematics" not in r.to_dict()  # the result schema changes in BE-B, not here
