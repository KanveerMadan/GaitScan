def classify_activity(df):
    """
    Analyses gait metrics from angle DataFrame and classifies
    the activity type with confidence score and plain English explanation.
    """

   
    duration = df["time_s"].max()
    fps = len(df) / duration if duration > 0 else 30

    
    knee_series = df["knee_L"].values
    steps = sum(1 for i in range(1, len(knee_series))
                if knee_series[i] > 155 and knee_series[i-1] <= 155)
    cadence = round((steps / duration) * 60, 1) if duration > 0 else 0

    
    knee_min_L = df["knee_L"].min()
    knee_min_R = df["knee_R"].min()
    avg_knee_min = (knee_min_L + knee_min_R) / 2
    knee_flexion = round(180 - avg_knee_min, 1)


    knee_avg_L = df["knee_L"].mean()
    knee_avg_R = df["knee_R"].mean()
    asymmetry = abs(knee_avg_L - knee_avg_R) / ((knee_avg_L + knee_avg_R) / 2) * 100

    
    from scipy.signal import find_peaks
    import numpy as np
    ankle_y = df["lm27_y"].values
    peaks, _ = find_peaks(ankle_y, distance=int(fps * 0.25), prominence=0.01)
    if len(peaks) > 2:
        intervals = np.diff(peaks)
        cadence_irregularity = round(np.std(intervals) / np.mean(intervals) * 100, 1)
    else:
        cadence_irregularity = 0

    
    activity = None
    confidence = 0
    description = ""
    icon = ""

    
    if asymmetry > 15 and cadence_irregularity > 25:
        activity = "Limping"
        icon = "🦿"
        confidence = min(95, int(50 + asymmetry + cadence_irregularity / 2))
        description = (
            f"Significant left-right asymmetry ({asymmetry:.1f}%) detected alongside "
            f"irregular step timing. One leg appears to be compensating for the other. "
            f"This pattern is consistent with a limp."
        )

    
    elif cadence > 150 and knee_flexion > 70:
        activity = "Running"
        icon = "🏃"
        confidence = min(95, int(60 + (cadence - 150) / 2 + (knee_flexion - 70) / 2))
        description = (
            f"High step rate ({cadence} steps/min) and deep knee flexion "
            f"({knee_flexion}°) detected. This is consistent with running."
        )

    
    elif cadence > 120 and knee_flexion > 55:
        activity = "Brisk Walking"
        icon = "🚶‍♂️"
        confidence = min(95, int(55 + (cadence - 120) / 2))
        description = (
            f"Elevated step rate ({cadence} steps/min) with good knee drive "
            f"({knee_flexion}°). This is consistent with brisk or purposeful walking."
        )

    
    elif cadence > 60 and knee_flexion > 35:
        activity = "Walking"
        icon = "🚶"
        confidence = min(95, int(50 + min(cadence, 120) / 4))
        description = (
            f"Normal step rate ({cadence} steps/min) and knee movement "
            f"({knee_flexion}°). This is consistent with regular walking."
        )

    
    else:
        activity = "Unknown"
        icon = "❓"
        confidence = 30
        description = (
            f"Could not confidently classify the activity. "
            f"Detected {cadence} steps/min cadence and {knee_flexion}° knee flexion. "
            f"Ensure the full body is visible and the video is at least 5 seconds long."
        )

    return {
        "activity": activity,
        "icon": icon,
        "confidence": confidence,
        "description": description,
        "metrics": {
            "cadence": cadence,
            "knee_flexion_range": knee_flexion,
            "asymmetry_index": round(asymmetry, 1),
            "cadence_irregularity": cadence_irregularity
        }
    }