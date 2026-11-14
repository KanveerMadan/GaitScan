"""Gait profile v3 (Plan V3 Phase 11, BE-B): the measurements an analysis stores, the references they're
compared with, the thresholds and the overall verdict. Owner decisions D1-D8 (2026-11-13), B and A
(2026-11-14): no symmetry, no per-side values; pelvis oscillation stored but not shown."""

import pytest
from gaitcore.norms import cadence_reference, same_method_reference
from gaitcore.norms.thresholds import KEY_METRICS, MIN_VERDICT_STEPS, level
from gaitcore.verdict import assess
from synthetic import synthetic_clip

from gaitcore import __version__
from gaitcore.pipeline import analyse


def profile():
    r = analyse(synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0])
    assert r.accepted
    return r.to_dict()["gait_profile"]


# ---- schema ---------------------------------------------------------------------------------------
def test_an_accepted_walk_stores_a_versioned_gait_profile():
    assert __version__ == "3.0.0"
    p = profile()
    assert p["schema"] == 3
    assert {"cadence", "step_time", "step_time_cv", "stance_pct", "swing_pct", "double_support_pct"} <= set(
        p["timing"]
    )
    k = p["kinematics"]
    for name in (
        "knee_ic",
        "knee_peak_swing",
        "knee_rom",
        "hip_rom",
        "hip_peak_ext",
        "hip_peak_flex",
        "ankle_rom",
    ):
        assert k[name]["value"] is not None and k[name]["n"] >= 3, name
    for joint in ("knee", "hip", "ankle"):
        assert len(k["curves"][joint]["mean"]) == 101 and len(k["curves"][joint]["sd"]) == 101
    assert p["hidden"]["pelvis_oscillation"]["value"] > 0  # stored, not shown (owner, 2026-11-14)
    assert "pelvis_oscillation" not in k
    assert set(p["poses"]) == {"heel_strike", "toe_off"}
    pose = p["poses"]["heel_strike"]
    assert {"pelvis", "shoulders", "lead", "trail"} <= set(pose)
    assert pose["pelvis"] == [0.0, 0.0] and set(pose["lead"]) == {"knee", "ankle", "heel", "toe"}
    q = p["quality"]
    assert (
        q["steps"] >= MIN_VERDICT_STEPS
        and 0 < q["usable_frame_fraction"] <= 1
        and 0 < q["leg_visibility"] <= 1
    )
    assert "left" not in str(p) and "symmetry" not in str(p)  # no per-side values, no symmetry (A)


def test_a_rejected_clip_or_a_treadmill_test_has_no_gait_profile():
    assert analyse(synthetic_clip(fps=15)[0]).to_dict()["gait_profile"] is None
    t = analyse(
        synthetic_clip(treadmill=True, passes=1, pass_secs=12.0), test="treadmill", belt_speed_m_s=1.2
    )
    assert t.to_dict()["gait_profile"] is None


# ---- references -----------------------------------------------------------------------------------
def test_cadence_reference_is_mobbs_by_sex_and_age_with_stated_fallbacks():
    r = cadence_reference("female", 45)
    assert (r.mean, r.sd, r.n, r.source, r.fallback) == (115.14, 8.75, 26, "mobbs2025", None)
    r = cadence_reference(None, 45)  # no sex: Table 3, both sexes, the same age group
    assert (r.mean, r.sd, r.fallback) == (111.75, 9.24, "no_sex")
    r = cadence_reference("male", 65)  # 6 men aged 61-70: too few; both sexes of that age instead
    assert (r.mean, r.sd, r.fallback) == (115.91, 7.85, "no_sex")
    for sex, age in ((None, None), ("female", None), ("female", 85)):
        r = cadence_reference(sex, age)
        assert r.fallback == "all_adults" and r.group == "all adults" and 105 < r.mean < 115


def test_same_method_references_come_from_healthy_ljmu_walkers():
    r = same_method_reference("knee_rom", None, None)
    assert r.source == "ljmu_same_method" and r.group == "all adults" and r.n >= 30
    assert 45 < r.mean < 70 and 0 < r.sd < 15
    assert same_method_reference("step_time_cv", None, None) is not None
    assert same_method_reference("no_such_metric", None, None) is None
    r = same_method_reference("knee_rom", "female", 70)  # no LJMU walkers over 65
    assert r.fallback == "all_adults"


# ---- thresholds -----------------------------------------------------------------------------------
class Ref:
    def __init__(self, mean, sd, kind="same_method", error_95=0.0):
        self.mean, self.sd, self.kind, self.error_95 = mean, sd, kind, error_95


@pytest.mark.parametrize(
    "x, want",
    [
        (100, "typical"),
        (120, "typical"),
        (120.01, "slightly_outside"),
        (130, "slightly_outside"),
        (130.01, "clearly_outside"),
        (80, "typical"),
        (69.9, "clearly_outside"),
    ],
)
def test_same_method_bands_are_two_and_three_sds(x, want):
    assert level(x, Ref(100, 10))[0] == want


def test_literature_bands_add_the_methods_error_so_an_unresolvable_difference_never_counts():
    ref = Ref(110, 9, kind="literature", error_95=4.5)
    assert level(110 + 2 * 9 + 4.5, ref)[0] == "typical"
    assert level(110 + 2 * 9 + 4.6, ref)[0] == "slightly_outside"
    assert level(110 - 3 * 9 - 4.6, ref)[0] == "clearly_outside"
    assert level(110 - 3 * 9 - 4.6, ref)[1] == "below"


def test_step_time_variability_is_only_outside_when_it_is_high():
    assert level(0.0, Ref(5, 2), one_sided="above")[0] == "typical"
    assert level(12, Ref(5, 2), one_sided="above")[0] == "clearly_outside"


# ---- the overall verdict --------------------------------------------------------------------------
def fake(values, steps=20, vis=0.9, n=8):
    """A profile with the key metrics at chosen z-scores against simple references."""
    timing = {
        "cadence": {"value": values.get("cadence", 110.0), "n": steps},
        "step_time_cv": {"value": values.get("step_time_cv", 3.0), "n": steps},
    }
    kin = {
        m: {"value": values.get(m, 0.0), "n": n}
        for m in (
            "knee_peak_swing",
            "knee_rom",
            "hip_rom",
            "hip_peak_ext",
            "ankle_rom",
            "knee_ic",
            "hip_peak_flex",
        )
    }
    return {
        "schema": 3,
        "timing": timing,
        "kinematics": kin,
        "quality": {"steps": steps, "usable_frame_fraction": 0.6, "leg_visibility": vis},
    }


def refs(metric, sex, age):
    return {"cadence": Ref(110, 9, "literature", 4.5), "step_time_cv": Ref(3, 1)}.get(metric, Ref(0, 1))


def test_all_key_metrics_typical_looks_typical():
    v = assess(fake({}), None, refs)
    assert v["overall"] == "typical" and v["drivers"] == []
    assert set(v["metrics"]) >= set(KEY_METRICS)


def test_one_metric_outside_is_worth_keeping_an_eye_on():
    assert assess(fake({"knee_rom": 2.5}), None, refs)["overall"] == "keep_an_eye"
    v = assess(fake({"knee_rom": -3.5}), None, refs)
    assert v["overall"] == "keep_an_eye" and v["drivers"] == ["knee_rom"]


def test_two_metrics_clearly_outside_is_outside_the_typical_range():
    v = assess(fake({"knee_rom": -3.5, "hip_rom": -4.0}), None, refs)
    assert v["overall"] == "outside" and set(v["drivers"]) == {"knee_rom", "hip_rom"}


def test_information_only_metrics_never_change_the_verdict():
    v = assess(fake({"ankle_rom": 9.0, "knee_ic": 9.0, "hip_peak_flex": 9.0}), None, refs)
    assert v["overall"] == "typical"
    assert v["metrics"]["ankle_rom"]["level"] is None  # information: no level (D3)


def test_low_confidence_metrics_are_shown_but_not_counted():
    v = assess(fake({"knee_rom": -4.0, "hip_rom": -4.0}, vis=0.5), None, refs)
    assert v["metrics"]["knee_rom"]["confidence"] == "low"
    assert v["overall"] == "typical" or v["overall"] is None


def test_too_little_walking_gives_no_verdict_and_says_how_to_re_record():
    v = assess(fake({}, steps=MIN_VERDICT_STEPS - 1), None, refs)
    assert v["overall"] is None and v["no_verdict"] == "too_few_steps"
    assert "walk_more_passes" in v["tips"]
