from typing import TypedDict

import pandas as pd


class ModeConfig(TypedDict):
    knee_si_flag: int
    knee_si_mild: int
    hip_si_flag: int
    hip_si_mild: int
    knee_flex_walk: int
    knee_flex_run: int
    # activity -> (low, high, note), cadence in steps/min
    cadence_ranges: dict[str, tuple[int, int, str]]
    description: str


class Finding(TypedDict):
    metric: str
    value: str
    status: str  # good | mild | flagged
    plain_english: str


class ScoringResult(TypedDict):
    scores: dict[str, float]
    findings: list[Finding]
    recommendations: list[str]
    risk_label: str
    risk_meaning: str
    risk_color: str
    mode: str
    mode_description: str


MODE_CONFIGS: dict[str, ModeConfig] = {
    "Clinical": {
        "knee_si_flag": 20,
        "knee_si_mild": 10,
        "hip_si_flag": 20,
        "hip_si_mild": 10,
        "knee_flex_walk": 45,
        "knee_flex_run": 70,
        "cadence_ranges": {
            "Walking": (80, 120, "Reference walking cadence: 80–120 steps/min."),
            "Brisk Walking": (120, 140, "Reference brisk-walking cadence: 120–140 steps/min."),
            "Running": (160, 200, "Reference running cadence: 160–180 steps/min."),
            "Asymmetric Walking": (0, 200, "No cadence reference is applied to asymmetric walking."),
        },
        "description": "General reference thresholds (not clinically validated).",
    },
    "Runner": {
        "knee_si_flag": 15,
        "knee_si_mild": 8,
        "hip_si_flag": 15,
        "hip_si_mild": 8,
        "knee_flex_walk": 50,
        "knee_flex_run": 80,
        "cadence_ranges": {
            "Walking": (80, 120, "Reference walking cadence: 80–120 steps/min."),
            "Brisk Walking": (150, 170, "Reference brisk-walking cadence for runners: 150–170 steps/min."),
            "Running": (170, 200, "Reference running cadence for runners: 170–180+ steps/min."),
            "Asymmetric Walking": (0, 200, "No cadence reference is applied to asymmetric walking."),
        },
        "description": "Tighter symmetry and higher cadence reference ranges for runners (not clinically validated).",
    },
    "Athlete": {
        "knee_si_flag": 10,
        "knee_si_mild": 5,
        "hip_si_flag": 10,
        "hip_si_mild": 5,
        "knee_flex_walk": 55,
        "knee_flex_run": 85,
        "cadence_ranges": {
            "Walking": (90, 120, "Reference walking cadence for athletes: 90–120 steps/min."),
            "Brisk Walking": (155, 175, "Reference brisk-walking cadence for athletes: 155–175 steps/min."),
            "Running": (175, 210, "Reference running cadence for athletes: 175–200+ steps/min."),
            "Asymmetric Walking": (0, 200, "No cadence reference is applied to asymmetric walking."),
        },
        "description": "Strictest reference ranges (not clinically validated).",
    },
    "Elderly": {
        "knee_si_flag": 25,
        "knee_si_mild": 15,
        "hip_si_flag": 25,
        "hip_si_mild": 15,
        "knee_flex_walk": 35,
        "knee_flex_run": 60,
        "cadence_ranges": {
            "Walking": (60, 100, "Reference walking cadence for older adults: 60–100 steps/min."),
            "Brisk Walking": (
                100,
                130,
                "Reference brisk-walking cadence for older adults: 100–130 steps/min.",
            ),
            "Running": (140, 180, "Reference running cadence for older adults: 140–170 steps/min."),
            "Asymmetric Walking": (0, 200, "No cadence reference is applied to asymmetric walking."),
        },
        "description": "Wider reference ranges intended for older adults (not clinically validated).",
    },
}


DISCLAIMER = (
    "GaitScan is an experimental measurement tool, not a medical device. "
    "It does not diagnose conditions or predict outcomes, and its measurements "
    "have not been clinically validated. A qualified clinician should interpret them."
)


def summary_for_score(score: float | None) -> tuple[str, str, str]:
    """Neutral (label, meaning, colour) for a stored deviation score.

    The score only counts how many measurements fell outside the reference
    ranges below. It is not a risk estimate (see ADR-005; removed in Phase 2).
    """
    if not score:
        return (
            "Within reference ranges",
            "All measurements in this recording fell within the reference ranges used. "
            "This is not a health assessment.",
            "green",
        )
    if score <= 25:
        return (
            "Minor deviations",
            "One or two measurements were near or outside the reference ranges used. "
            "A clinician can interpret this in context.",
            "green",
        )
    if score <= 50:
        return (
            "Several deviations",
            "Some measurements were outside the reference ranges used. "
            "A clinician can interpret these in context.",
            "amber",
        )
    return (
        "Many deviations",
        "Many measurements were outside the reference ranges used. "
        "Consider reviewing this recording with a physiotherapist.",
        "amber",
    )


def calculate_risk_scores(
    df: pd.DataFrame, activity: str = "Walking", mode: str = "Clinical"
) -> ScoringResult:
    """
    Compare whole-clip gait measurements against the reference ranges of `mode`.

    Returns per-metric findings (status good / mild / flagged = within / near /
    outside the reference range) and a summary. The additive deviation score is
    kept only for backwards compatibility and is not shown to users.
    """

    cfg = MODE_CONFIGS.get(mode, MODE_CONFIGS["Clinical"])

    scores: dict[str, float] = {}
    findings: list[Finding] = []
    recommendations: list[str] = []
    risk = 0

    knee_avg_L = df["knee_L"].mean()
    knee_avg_R = df["knee_R"].mean()
    knee_si = abs(knee_avg_L - knee_avg_R) / ((knee_avg_L + knee_avg_R) / 2) * 100

    hip_avg_L = df["hip_L"].mean()
    hip_avg_R = df["hip_R"].mean()
    hip_si = abs(hip_avg_L - hip_avg_R) / ((hip_avg_L + hip_avg_R) / 2) * 100

    scores["knee_symmetry_index"] = round(knee_si, 1)
    scores["hip_symmetry_index"] = round(hip_si, 1)

    if knee_si > cfg["knee_si_flag"]:
        risk += 30
        findings.append(
            {
                "metric": "Knee Symmetry",
                "value": f"{knee_si:.1f}%",
                "status": "flagged",
                "plain_english": (
                    f"Left and right knee motion differed by {knee_si:.0f}% in this recording "
                    f"(reference for {mode} mode: under {cfg['knee_si_flag']}%)."
                ),
            }
        )
        recommendations.append("Single-leg strengthening exercises to balance both sides")
    elif knee_si > cfg["knee_si_mild"]:
        risk += 15
        findings.append(
            {
                "metric": "Knee Symmetry",
                "value": f"{knee_si:.1f}%",
                "status": "mild",
                "plain_english": (
                    f"Left and right knee motion differed by {knee_si:.0f}% in this recording, "
                    f"near the edge of the {mode} reference (under {cfg['knee_si_mild']}%)."
                ),
            }
        )
    else:
        findings.append(
            {
                "metric": "Knee Symmetry",
                "value": f"{knee_si:.1f}%",
                "status": "good",
                "plain_english": "Left and right knee motion were similar in this recording.",
            }
        )

    if hip_si > cfg["hip_si_flag"]:
        risk += 20
        findings.append(
            {
                "metric": "Hip Symmetry",
                "value": f"{hip_si:.1f}%",
                "status": "flagged",
                "plain_english": (
                    f"Left and right hip motion differed by {hip_si:.0f}% in this recording "
                    f"(reference for {mode} mode: under {cfg['hip_si_flag']}%)."
                ),
            }
        )
        recommendations.append("Hip mobility and strengthening exercises")
    elif hip_si > cfg["hip_si_mild"]:
        risk += 10
        findings.append(
            {
                "metric": "Hip Symmetry",
                "value": f"{hip_si:.1f}%",
                "status": "mild",
                "plain_english": (
                    f"Left and right hip motion differed by {hip_si:.0f}% in this recording, "
                    f"near the edge of the {mode} reference (under {cfg['hip_si_mild']}%)."
                ),
            }
        )
    else:
        findings.append(
            {
                "metric": "Hip Symmetry",
                "value": f"{hip_si:.1f}%",
                "status": "good",
                "plain_english": "Left and right hip motion were similar in this recording.",
            }
        )

    knee_min_L = df["knee_L"].min()
    knee_min_R = df["knee_R"].min()
    knee_flexion_L = round(180 - knee_min_L, 1)
    knee_flexion_R = round(180 - knee_min_R, 1)

    scores["knee_flexion_range_L"] = knee_flexion_L
    scores["knee_flexion_range_R"] = knee_flexion_R

    if activity == "Running":
        thresh = cfg["knee_flex_run"]
        if knee_flexion_L < thresh or knee_flexion_R < thresh:
            risk += 20
            findings.append(
                {
                    "metric": "Knee Drive",
                    "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                    "status": "flagged",
                    "plain_english": (
                        f"Peak knee bend while running was below the {thresh}° reference for {mode} mode."
                    ),
                }
            )
            recommendations.append("High-knees drills to practise running knee drive")
        else:
            findings.append(
                {
                    "metric": "Knee Drive",
                    "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                    "status": "good",
                    "plain_english": "Peak knee bend while running was within the reference range.",
                }
            )

    elif activity == "Asymmetric Walking":
        risk += 25
        less_moving = "left" if knee_flexion_L < knee_flexion_R else "right"
        findings.append(
            {
                "metric": "Less-moving Side",
                "value": less_moving.capitalize(),
                "status": "flagged",
                "plain_english": (
                    f"The {less_moving} knee showed less range of motion than the other "
                    f"side in this recording."
                ),
            }
        )
        recommendations.append("Review this recording with a physiotherapist")

    else:
        thresh = cfg["knee_flex_walk"]
        if knee_flexion_L < thresh or knee_flexion_R < thresh:
            risk += 20
            findings.append(
                {
                    "metric": "Knee Flexion",
                    "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                    "status": "flagged",
                    "plain_english": (
                        f"Peak knee bend while walking was below the {thresh}° reference for {mode} mode."
                    ),
                }
            )
            recommendations.append("Knee mobility exercises")
        else:
            findings.append(
                {
                    "metric": "Knee Flexion",
                    "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                    "status": "good",
                    "plain_english": "Peak knee bend while walking was within the reference range.",
                }
            )

    duration = df["time_s"].max()
    knee_series = df["knee_L"].values
    steps = sum(1 for i in range(1, len(knee_series)) if knee_series[i] > 155 and knee_series[i - 1] <= 155)
    cadence = round((steps / duration) * 60, 1) if duration > 0 else 0
    scores["cadence"] = cadence

    low, high, cadence_note = cfg["cadence_ranges"].get(activity, (80, 120, ""))

    if cadence < low and activity != "Asymmetric Walking":
        risk += 10
        findings.append(
            {
                "metric": "Cadence",
                "value": f"{cadence} steps/min",
                "status": "mild",
                "plain_english": (
                    f"Step rate was {cadence} steps/min, below the {mode} reference. {cadence_note}"
                ),
            }
        )
    else:
        findings.append(
            {
                "metric": "Cadence",
                "value": f"{cadence} steps/min",
                "status": "good",
                "plain_english": f"Step rate was {cadence} steps/min. {cadence_note}",
            }
        )

    risk = min(risk, 100)
    scores["overall_risk_score"] = risk
    risk_label, risk_meaning, risk_color = summary_for_score(risk)

    return {
        "scores": scores,
        "findings": findings,
        "recommendations": recommendations,
        "risk_label": risk_label,
        "risk_meaning": risk_meaning,
        "risk_color": risk_color,
        "mode": mode,
        "mode_description": cfg["description"],
    }
