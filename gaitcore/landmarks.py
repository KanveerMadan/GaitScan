import logging

import cv2
import mediapipe as mp
import pandas as pd
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

from gaitcore import model

log = logging.getLogger(__name__)


class VideoReadError(ValueError):
    """The file could not be decoded as a video."""


def _options() -> PoseLandmarkerOptions:
    # Same thresholds as the legacy mp.solutions.pose defaults the app used (0.5 each).
    return PoseLandmarkerOptions(
        # CPU explicitly: the server has no GPU, and on macOS the default graph tries Metal and aborts.
        base_options=BaseOptions(model_asset_path=str(model.model_path()), delegate=BaseOptions.Delegate.CPU),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )


def extract_landmarks(video_path: str) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise VideoReadError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    log.info(f"Video loaded: {total} frames at {fps:.1f} fps")

    with PoseLandmarker.create_from_options(_options()) as landmarker:
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            # VIDEO mode needs strictly increasing timestamps in ms.
            result = landmarker.detect_for_video(image, round(idx * 1000 / fps))

            if result.pose_landmarks:
                row: dict[str, float] = {"frame": idx, "time_s": round(idx / fps, 4)}
                for i, lm in enumerate(result.pose_landmarks[0]):
                    row[f"lm{i}_x"] = round(lm.x, 6)
                    row[f"lm{i}_y"] = round(lm.y, 6)
                    row[f"lm{i}_z"] = round(lm.z, 6)
                    row[f"lm{i}_vis"] = round(lm.visibility, 4)
                rows.append(row)

            idx += 1

    cap.release()
    log.info(f"Done: landmarks extracted from {len(rows)}/{total} frames")
    return pd.DataFrame(rows)
