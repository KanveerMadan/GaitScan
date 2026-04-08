import cv2
import mediapipe as mp
import pandas as pd

mp_pose = mp.solutions.pose

def extract_landmarks(video_path):
    rows = []
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  Video loaded: {total} frames at {fps:.1f} fps")

    with mp_pose.Pose(min_detection_confidence=0.5) as pose:
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            if results.pose_landmarks:
                row = {"frame": idx, "time_s": round(idx / fps, 4)}
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    row[f"lm{i}_x"] = round(lm.x, 6)
                    row[f"lm{i}_y"] = round(lm.y, 6)
                    row[f"lm{i}_z"] = round(lm.z, 6)
                    row[f"lm{i}_vis"] = round(lm.visibility, 4)
                rows.append(row)

            idx += 1

    cap.release()
    print(f"  Done: landmarks extracted from {len(rows)}/{total} frames")
    return pd.DataFrame(rows)