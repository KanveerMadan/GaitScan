MODE_CONFIGS = {
    "Clinical": {
        "knee_si_flag":    20,   
        "knee_si_mild":    10,
        "hip_si_flag":     20,
        "hip_si_mild":     10,
        "knee_flex_walk":  45,   
        "knee_flex_run":   70,   
        "cadence_ranges": {
            "Walking":       (80,  120, "A healthy walking cadence is 80–120 steps/min."),
            "Brisk Walking": (120, 140, "A healthy brisk walking cadence is 120–140 steps/min."),
            "Running":       (160, 200, "An efficient running cadence is 160–180 steps/min."),
            "Limping":       (0,   200, "Cadence varies when limping."),
        },
        "description": "Standard clinical assessment thresholds."
    },
    "Runner": {
        
        "knee_si_flag":    15,
        "knee_si_mild":    8,
        "hip_si_flag":     15,
        "hip_si_mild":     8,
        "knee_flex_walk":  50,
        "knee_flex_run":   80,   
        "cadence_ranges": {
            "Walking":       (80,  120, "A healthy walking cadence is 80–120 steps/min."),
            "Brisk Walking": (150, 170, "Elite brisk-walking cadence is 150–170 steps/min."),
            "Running":       (170, 200, "Optimal running cadence is 170–180+ steps/min."),
            "Limping":       (0,   200, "Cadence varies when limping."),
        },
        "description": "Optimised for runners — tighter symmetry and higher cadence targets."
    },
    "Athlete": {
        
        "knee_si_flag":    10,
        "knee_si_mild":    5,
        "hip_si_flag":     10,
        "hip_si_mild":     5,
        "knee_flex_walk":  55,
        "knee_flex_run":   85,
        "cadence_ranges": {
            "Walking":       (90,  120, "Athletes should maintain 90–120 steps/min at walking pace."),
            "Brisk Walking": (155, 175, "Athletic brisk-walking target is 155–175 steps/min."),
            "Running":       (175, 210, "High-performance running cadence is 175–200+ steps/min."),
            "Limping":       (0,   200, "Cadence varies when limping."),
        },
        "description": "High-performance mode — flags even minor asymmetries for peak optimisation."
    },
    "Elderly": {
        
        "knee_si_flag":    25,
        "knee_si_mild":    15,
        "hip_si_flag":     25,
        "hip_si_mild":     15,
        "knee_flex_walk":  35,   
        "knee_flex_run":   60,
        "cadence_ranges": {
            "Walking":       (60,  100, "A safe walking cadence for older adults is 60–100 steps/min."),
            "Brisk Walking": (100, 130, "A healthy brisk-walking cadence is 100–130 steps/min."),
            "Running":       (140, 180, "A comfortable running cadence is 140–170 steps/min."),
            "Limping":       (0,   200, "Cadence varies when limping."),
        },
        "description": "Adjusted for older adults — prioritises fall risk and stability over performance."
    },
}


def calculate_risk_scores(df, activity="Walking", mode="Clinical"):
    """
    Activity-aware and mode-aware risk scoring with plain English explanations.

    Mode changes the thresholds at which findings are flagged:
      Clinical  — standard physiotherapy thresholds (default)
      Runner    — tighter symmetry, higher cadence targets
      Athlete   — strictest thresholds for peak performance
      Elderly   — more lenient, focused on fall risk and stability

    Score 0-100 where:
      0     = No issues. Your gait looks healthy.
      1-25  = Minor findings. Worth monitoring.
      26-50 = Moderate concern. Consider a physiotherapist.
      51-75 = Significant issues. Physiotherapy recommended.
      76-100= Serious abnormality. Please consult a doctor.
    """

    cfg = MODE_CONFIGS.get(mode, MODE_CONFIGS["Clinical"])

    scores = {}
    findings = []
    recommendations = []
    risk = 0

    knee_avg_L = df["knee_L"].mean()
    knee_avg_R = df["knee_R"].mean()
    knee_si = abs(knee_avg_L - knee_avg_R) / ((knee_avg_L + knee_avg_R) / 2) * 100

    hip_avg_L = df["hip_L"].mean()
    hip_avg_R = df["hip_R"].mean()
    hip_si = abs(hip_avg_L - hip_avg_R) / ((hip_avg_L + hip_avg_R) / 2) * 100

    scores["knee_symmetry_index"] = round(knee_si, 1)
    scores["hip_symmetry_index"]  = round(hip_si, 1)

    if knee_si > cfg["knee_si_flag"]:
        risk += 30
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "flagged",
            "plain_english": (
                f"Your left and right knees are moving very differently — "
                f"a {knee_si:.0f}% difference. This means one knee is doing "
                f"significantly more work than the other, which can cause "
                f"long-term joint damage and pain."
                + (f" (Threshold for {mode} mode: {cfg['knee_si_flag']}%)" if mode != "Clinical" else "")
            )
        })
        recommendations.append("Single-leg strengthening exercises to balance both sides")
    elif knee_si > cfg["knee_si_mild"]:
        risk += 15
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "mild",
            "plain_english": (
                f"Mild difference between your left and right knee movement "
                f"({knee_si:.0f}%). Worth monitoring — if you notice "
                f"knee pain on one side, this could be the cause."
            )
        })
    else:
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "good",
            "plain_english": "Both knees are moving very similarly. Good left-right balance."
        })

    if hip_si > cfg["hip_si_flag"]:
        risk += 20
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "flagged",
            "plain_english": (
                f"Significant difference between left and right hip movement "
                f"({hip_si:.0f}%). This can indicate hip weakness or tightness "
                f"on one side, and often contributes to lower back pain over time."
            )
        })
        recommendations.append("Hip mobility and strengthening exercises")
    elif hip_si > cfg["hip_si_mild"]:
        risk += 10
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "mild",
            "plain_english": f"Slight hip asymmetry detected ({hip_si:.0f}%). Within acceptable range but worth monitoring."
        })
    else:
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "good",
            "plain_english": "Both hips are moving evenly. No asymmetry detected."
        })

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
            findings.append({
                "metric": "Knee Drive",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "flagged",
                "plain_english": (
                    f"Your knee isn't bending enough while running (target: >{thresh}° for {mode} mode). "
                    f"This 'shuffling' pattern wastes energy and increases "
                    f"injury risk — especially shin splints and knee pain."
                )
            })
            recommendations.append("High knees drills to improve running knee drive")
        else:
            findings.append({
                "metric": "Knee Drive",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "good",
                "plain_english": "Good knee drive detected. Your running form looks efficient."
            })

    elif activity == "Limping":
        risk += 25
        worse_side = "left" if knee_flexion_L < knee_flexion_R else "right"
        findings.append({
            "metric": "Affected Side",
            "value": worse_side.capitalize(),
            "status": "flagged",
            "plain_english": (
                f"Your {worse_side} side shows reduced movement range, "
                f"suggesting it is the affected leg. The opposite leg is "
                f"likely compensating, which can cause secondary pain over time."
            )
        })
        recommendations.append("Consult a physiotherapist to identify the underlying cause")
        recommendations.append("Avoid high-impact activities until assessed")

    else:
        thresh = cfg["knee_flex_walk"]
        if knee_flexion_L < thresh or knee_flexion_R < thresh:
            risk += 20
            findings.append({
                "metric": "Knee Flexion",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "flagged",
                "plain_english": (
                    f"Your knees are not bending enough during walking (target: >{thresh}° for {mode} mode). "
                    f"This 'stiff-legged' pattern puts extra stress on your "
                    f"joints and increases fall risk, especially on uneven surfaces."
                )
            })
            recommendations.append("Knee mobility exercises to improve walking pattern")
        else:
            findings.append({
                "metric": "Knee Flexion",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "good",
                "plain_english": "Your knees are bending well during each step. Good range of motion detected."
            })

    duration    = df["time_s"].max()
    knee_series = df["knee_L"].values
    steps = sum(
        1 for i in range(1, len(knee_series))
        if knee_series[i] > 155 and knee_series[i - 1] <= 155
    )
    cadence = round((steps / duration) * 60, 1) if duration > 0 else 0
    scores["cadence"] = cadence

    low, high, cadence_note = cfg["cadence_ranges"].get(activity, (80, 120, ""))

    if cadence < low and activity != "Limping":
        risk += 10
        findings.append({
            "metric": "Cadence",
            "value": f"{cadence} steps/min",
            "status": "mild",
            "plain_english": (
                f"Your step rate is lower than ideal for {mode} mode ({cadence} steps/min). "
                f"{cadence_note} A slower cadence can mean reduced efficiency "
                f"and more impact on your joints per step."
            )
        })
    else:
        findings.append({
            "metric": "Cadence",
            "value": f"{cadence} steps/min",
            "status": "good",
            "plain_english": f"Your step rate looks good ({cadence} steps/min). {cadence_note}"
        })

    risk = min(risk, 100)
    scores["overall_risk_score"] = risk

    if risk == 0:
        risk_label   = "No issues detected"
        risk_meaning = "Your gait looks healthy. No concerns found."
        risk_color   = "green"
    elif risk <= 25:
        risk_label   = "Minor findings"
        risk_meaning = "A few small things worth keeping an eye on, but nothing serious."
        risk_color   = "green"
    elif risk <= 50:
        risk_label   = "Moderate concern"
        risk_meaning = "Some gait issues detected. Worth seeing a physiotherapist, especially if you experience pain."
        risk_color   = "amber"
    elif risk <= 75:
        risk_label   = "Significant issues"
        risk_meaning = "Clear gait abnormalities detected. Physiotherapy is recommended."
        risk_color   = "red"
    else:
        risk_label   = "Serious abnormality"
        risk_meaning = "Serious gait issues detected. Please consult a doctor or physiotherapist soon."
        risk_color   = "red"

    return {
        "scores":          scores,
        "findings":        findings,
        "recommendations": recommendations,
        "risk_label":      risk_label,
        "risk_meaning":    risk_meaning,
        "risk_color":      risk_color,
        "mode":            mode,
        "mode_description": cfg["description"],
    }