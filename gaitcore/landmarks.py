import logging

import cv2
import mediapipe as mp
import pandas as pd
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

from gaitcore import model
from gaitcore.clip import Clip

log = logging.getLogger(__name__)
# The pose model works on a 256x256 input; full-resolution frames only cost memory (512 MB on Render).
MAX_SIDE = 640


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


def extract_clip(video_path: str) -> Clip:
    """Every decoded frame -> one landmark row (NaN when nobody is detected), plus `n_poses`, the
    number of people found (up to 2: enough to know the frame is ambiguous)."""
    # One decoder thread: FFmpeg's default is one per visible CPU, each holding full-size frames,
    # and a shared host can show many CPUs to a small container.
    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    if not cap.isOpened():
        raise VideoReadError(f"Cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        cap.release()
        raise VideoReadError(f"No frame rate in: {video_path}")
    rows: list[dict[str, float]] = []
    width = height = 0
    options = _options()
    options.num_poses = 2
    with PoseLandmarker.create_from_options(options) as landmarker:
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            height, width = frame.shape[:2]
            scale = MAX_SIDE / max(width, height)
            if scale < 1:  # same aspect ratio, so normalised landmarks still map onto the original frame
                frame = cv2.resize(
                    frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
                )
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(image, round(idx * 1000 / fps))
            row: dict[str, float] = {"n_poses": float(len(result.pose_landmarks))}
            if result.pose_landmarks:
                for i, lm in enumerate(result.pose_landmarks[0]):
                    row[f"lm{i}_x"], row[f"lm{i}_y"] = lm.x, lm.y
                    row[f"lm{i}_z"], row[f"lm{i}_vis"] = lm.z, lm.visibility
            rows.append(row)
            idx += 1
    cap.release()
    if not rows:
        raise VideoReadError(f"No frames decoded from: {video_path}")
    cols = [f"lm{i}_{k}" for i in range(33) for k in ("x", "y", "z", "vis")] + ["n_poses"]
    df = pd.DataFrame(rows).reindex(columns=cols)
    log.info(f"Landmarks: {int((df['n_poses'] > 0).sum())}/{len(df)} frames with a pose")
    return Clip(landmarks=df, fps=fps, width=width, height=height)
