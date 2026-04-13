def calculate_risk_scores(df, activity="Walking"):
    """
    Activity-aware risk scoring with plain English explanations.
    Score 0-100 where:
      0     = No issues. Your gait looks healthy.
      1-25  = Minor findings. Worth monitoring.
      26-50 = Moderate concern. Consider a physiotherapist.
      51-75 = Significant issues. Physiotherapy recommended.
      76-100= Serious abnormality. Please consult a doctor.
    """

    scores = {}
    findings = []
    recommendations = []
    risk = 0

    # --- Symmetry Index ---
    knee_avg_L = df["knee_L"].mean()
    knee_avg_R = df["knee_R"].mean()
    knee_si = abs(knee_avg_L - knee_avg_R) / ((knee_avg_L + knee_avg_R) / 2) * 100

    hip_avg_L = df["hip_L"].mean()
    hip_avg_R = df["hip_R"].mean()
    hip_si = abs(hip_avg_L - hip_avg_R) / ((hip_avg_L + hip_avg_R) / 2) * 100

    scores["knee_symmetry_index"] = round(knee_si, 1)
    scores["hip_symmetry_index"] = round(hip_si, 1)

    # Knee symmetry findings
    if knee_si > 20:
        risk += 30
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "flagged",
            "plain_english": f"Your left and right knees are moving very differently — "
                           f"a {knee_si:.0f}% difference. This means one knee is doing "
                           f"significantly more work than the other, which can cause "
                           f"long-term joint damage and pain."
        })
        recommendations.append("Single-leg strengthening exercises to balance both sides")
    elif knee_si > 10:
        risk += 15
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "mild",
            "plain_english": f"Mild difference between your left and right knee movement "
                           f"({knee_si:.0f}%). This is worth monitoring — if you notice "
                           f"knee pain on one side, this could be the cause."
        })
    else:
        findings.append({
            "metric": "Knee Symmetry",
            "value": f"{knee_si:.1f}%",
            "status": "good",
            "plain_english": "Both knees are moving very similarly. Good left-right balance."
        })

    # Hip symmetry findings
    if hip_si > 20:
        risk += 20
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "flagged",
            "plain_english": f"Significant difference between left and right hip movement "
                           f"({hip_si:.0f}%). This can indicate hip weakness or tightness "
                           f"on one side, and often contributes to lower back pain over time."
        })
        recommendations.append("Hip mobility and strengthening exercises")
    elif hip_si > 10:
        risk += 10
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "mild",
            "plain_english": f"Slight hip asymmetry detected ({hip_si:.0f}%). "
                           f"Within acceptable range but worth monitoring."
        })
    else:
        findings.append({
            "metric": "Hip Symmetry",
            "value": f"{hip_si:.1f}%",
            "status": "good",
            "plain_english": "Both hips are moving evenly. No asymmetry detected."
        })

    # --- Activity-specific scoring ---
    knee_min_L = df["knee_L"].min()
    knee_min_R = df["knee_R"].min()
    knee_flexion_L = round(180 - knee_min_L, 1)
    knee_flexion_R = round(180 - knee_min_R, 1)

    scores["knee_flexion_range_L"] = knee_flexion_L
    scores["knee_flexion_range_R"] = knee_flexion_R

    if activity == "Running":
        # Runners need more flexion
        if knee_flexion_L < 70 or knee_flexion_R < 70:
            risk += 20
            findings.append({
                "metric": "Knee Drive",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "flagged",
                "plain_english": "Your knee isn't bending enough while running. "
                               "This 'shuffling' pattern wastes energy and increases "
                               "injury risk — especially shin splints and knee pain."
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
            "plain_english": f"Your {worse_side} side shows reduced movement range, "
                           f"suggesting it is the affected leg. The opposite leg is "
                           f"likely compensating, which can cause secondary pain over time."
        })
        recommendations.append("Consult a physiotherapist to identify the underlying cause")
        recommendations.append("Avoid high-impact activities until assessed")

    else:
        # Walking / Brisk Walking
        if knee_flexion_L < 45 or knee_flexion_R < 45:
            risk += 20
            findings.append({
                "metric": "Knee Flexion",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "flagged",
                "plain_english": "Your knees are not bending enough during walking. "
                               "This 'stiff-legged' pattern puts extra stress on your "
                               "joints and increases fall risk, especially on uneven surfaces."
            })
            recommendations.append("Knee mobility exercises to improve walking pattern")
        else:
            findings.append({
                "metric": "Knee Flexion",
                "value": f"L: {knee_flexion_L}° R: {knee_flexion_R}°",
                "status": "good",
                "plain_english": "Your knees are bending well during each step. "
                               "Good range of motion detected."
            })

    # --- Cadence ---
    duration = df["time_s"].max()
    knee_series = df["knee_L"].values
    steps = sum(1 for i in range(1, len(knee_series))
                if knee_series[i] > 155 and knee_series[i-1] <= 155)
    cadence = round((steps / duration) * 60, 1) if duration > 0 else 0
    scores["cadence"] = cadence
    
    cadence_ranges = {
        "Walking":       (80, 120, "A healthy walking cadence is 80–120 steps/min."),
        "Brisk Walking": (120, 140, "A healthy brisk walking cadence is 120–140 steps/min."),
        "Running":       (160, 200, "An efficient running cadence is 160–180 steps/min."),
        "Limping":       (0, 200,   "Cadence varies when limping.")
    }
    low, high, cadence_note = cadence_ranges.get(activity, (80, 120, ""))

    if cadence < low and activity != "Limping":
        risk += 10
        findings.append({
            "metric": "Cadence",
            "value": f"{cadence} steps/min",
            "status": "mild",
            "plain_english": f"Your step rate is lower than ideal ({cadence} steps/min). "
                           f"{cadence_note} A slower cadence can mean reduced efficiency "
                           f"and more impact on your joints per step."
        })
    else:
        findings.append({
            "metric": "Cadence",
            "value": f"{cadence} steps/min",
            "status": "good",
            "plain_english": f"Your step rate looks good ({cadence} steps/min). {cadence_note}"
        })

    # --- Final risk score ---
    risk = min(risk, 100)
    scores["overall_risk_score"] = risk

    # Plain English risk label
    if risk == 0:
        risk_label = "No issues detected"
        risk_meaning = "Your gait looks healthy. No concerns found."
        risk_color = "green"
    elif risk <= 25:
        risk_label = "Minor findings"
        risk_meaning = "A few small things worth keeping an eye on, but nothing serious."
        risk_color = "green"
    elif risk <= 50:
        risk_label = "Moderate concern"
        risk_meaning = "Some gait issues detected. Worth seeing a physiotherapist, especially if you experience pain."
        risk_color = "amber"
    elif risk <= 75:
        risk_label = "Significant issues"
        risk_meaning = "Clear gait abnormalities detected. Physiotherapy is recommended."
        risk_color = "red"
    else:
        risk_label = "Serious abnormality"
        risk_meaning = "Serious gait issues detected. Please consult a doctor or physiotherapist soon."
        risk_color = "red"

    return {
        "scores": scores,
        "findings": findings,
        "recommendations": recommendations,
        "risk_label": risk_label,
        "risk_meaning": risk_meaning,
        "risk_color": risk_color
    }