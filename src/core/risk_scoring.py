import pandas as pd

def calculate_risk_scores(df):
    """
    Takes angle DataFrame, returns a dict of clinical risk scores and findings.
    All thresholds based on published physiotherapy literature.
    """
    scores = {}
    findings = []
    recommendations = []

    knee_avg_L = df["knee_L"].mean()
    knee_avg_R = df["knee_R"].mean()
    knee_si = abs(knee_avg_L - knee_avg_R) / ((knee_avg_L + knee_avg_R) / 2) * 100

    hip_avg_L = df["hip_L"].mean()
    hip_avg_R = df["hip_R"].mean()
    hip_si = abs(hip_avg_L - hip_avg_R) / ((hip_avg_L + hip_avg_R) / 2) * 100

    scores["knee_symmetry_index"] = round(knee_si, 1)
    scores["hip_symmetry_index"] = round(hip_si, 1)

    if knee_si > 20:
        findings.append(f"Significant knee asymmetry detected ({knee_si:.1f}% difference between legs)")
        recommendations.append("Consult physiotherapist for knee symmetry evaluation")
    elif knee_si > 10:
        findings.append(f"Mild knee asymmetry ({knee_si:.1f}%) — monitor over time")

    if hip_si > 20:
        findings.append(f"Significant hip asymmetry ({hip_si:.1f}%)")
        recommendations.append("Hip strengthening exercises recommended")
    elif hip_si > 10:
        findings.append(f"Mild hip asymmetry ({hip_si:.1f}%) — within acceptable range")

    knee_min_L = df["knee_L"].min()
    knee_min_R = df["knee_R"].min()

    scores["knee_flexion_range_L"] = round(180 - knee_min_L, 1)
    scores["knee_flexion_range_R"] = round(180 - knee_min_R, 1)

    if knee_min_L > 130:
        findings.append(f"Left knee flexion limited — only {180-knee_min_L:.0f}° range (normal >50°)")
        recommendations.append("Left knee mobility exercises recommended")
    if knee_min_R > 130:
        findings.append(f"Right knee flexion limited — only {180-knee_min_R:.0f}° range (normal >50°)")
        recommendations.append("Right knee mobility exercises recommended")

    
    duration = df["time_s"].max()
    knee_series = df["knee_L"].values
    
    steps = sum(1 for i in range(1, len(knee_series))
                if knee_series[i] > 160 and knee_series[i-1] <= 160)
    cadence = round((steps / duration) * 60, 1) if duration > 0 else 0
    scores["estimated_cadence_steps_per_min"] = cadence

    if cadence < 80:
        findings.append(f"Low cadence ({cadence} steps/min) — normal walking is 100-120")
    elif cadence > 80:
        findings.append(f"Cadence {cadence} steps/min — within normal range")

    
    risk = 0
    if knee_si > 20: risk += 30
    elif knee_si > 10: risk += 15
    if hip_si > 20: risk += 20
    elif hip_si > 10: risk += 10
    if knee_min_L > 130: risk += 25
    if knee_min_R > 130: risk += 25

    scores["overall_risk_score"] = min(risk, 100)

    if not findings:
        findings.append("No significant gait abnormalities detected")

    return {
        "scores": scores,
        "findings": findings,
        "recommendations": recommendations
    }