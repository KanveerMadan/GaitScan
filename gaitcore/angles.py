import numpy as np
import pandas as pd

def angle_3pts(A, B, C):
    """
    Calculate angle at joint B given three (x, y) points A, B, C.
    Returns angle in degrees.
    """
    BA = np.array(A) - np.array(B)
    BC = np.array(C) - np.array(B)
    cos_a = np.dot(BA, BC) / (np.linalg.norm(BA) * np.linalg.norm(BC) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))

def _p(row, i):
    """Extract (x, y) for landmark i from a DataFrame row."""
    return (row[f"lm{i}_x"], row[f"lm{i}_y"])

def knee_angle_L(row):
    return angle_3pts(_p(row, 23), _p(row, 25), _p(row, 27))

def knee_angle_R(row):
    return angle_3pts(_p(row, 24), _p(row, 26), _p(row, 28))

def hip_angle_L(row):
    return angle_3pts(_p(row, 11), _p(row, 23), _p(row, 25))

def hip_angle_R(row):
    return angle_3pts(_p(row, 12), _p(row, 24), _p(row, 26))

def shoulder_tilt(row):
    return angle_3pts(_p(row, 11), _p(row, 12), (row["lm12_x"] + 0.1, row["lm12_y"]))

def add_all_angles(df):
    print("  Calculating joint angles...")
    df = df.copy()
    df["knee_L"] = df.apply(knee_angle_L, axis=1)
    df["knee_R"] = df.apply(knee_angle_R, axis=1)
    df["hip_L"]  = df.apply(hip_angle_L,  axis=1)
    df["hip_R"]  = df.apply(hip_angle_R,  axis=1)
    df["shoulder_tilt"] = df.apply(shoulder_tilt, axis=1)
    print(f"  Done: 5 angles calculated for {len(df)} frames")
    return df