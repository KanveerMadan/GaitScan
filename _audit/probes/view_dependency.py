"""How much does camera yaw change the app's 2D knee angle for the same 3D knee?
Orthographic camera; leg moves in the sagittal plane (x forward, y down, z lateral).
yaw 0 = pure side view, 90 = walking straight toward the camera.
"""
import os, sys, math
sys.path.insert(0, os.getcwd())
from src.core.calculate_angles import angle_3pts

THIGH, SHANK = 0.45, 0.43
def leg(hip_flex_deg, knee_flex_deg, z=0.1):
    h = math.radians(hip_flex_deg); k = math.radians(knee_flex_deg)
    hip = (0.0, 0.0, z)
    knee = (THIGH * math.sin(h), THIGH * math.cos(h), z)
    a = h - k   # shank direction
    ankle = (knee[0] + SHANK * math.sin(a), knee[1] + SHANK * math.cos(a), z)
    return hip, knee, ankle

def project(p, yaw):
    y = math.radians(yaw)
    return (p[0] * math.cos(y) + p[2] * math.sin(y), p[1])

print("true_knee_flexion | app-reported flexion at camera yaw 0/15/30/45/60/75/90 deg")
for true_flex in (10, 30, 60):
    hip, knee, ankle = leg(20, true_flex)
    row = []
    for yaw in (0, 15, 30, 45, 60, 75, 90):
        ang = angle_3pts(project(hip, yaw), project(knee, yaw), project(ankle, yaw))
        row.append(round(180 - ang, 1))
    print(f"{true_flex:>5} deg          | {row}")
