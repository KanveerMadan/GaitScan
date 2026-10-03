from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Clip:
    """Pose landmarks for one video, as MediaPipe returns them.

    `landmarks` has one row per decoded frame, in order. Columns `lm{i}_x`, `lm{i}_y` are normalised
    (x / width, y / height), `lm{i}_z` is MediaPipe's relative depth and `lm{i}_vis` its visibility.
    Frames without a detected pose are rows of NaN. Optional column `n_poses`: people detected in
    that frame. Frame i is at time i / fps.
    """

    landmarks: pd.DataFrame
    fps: float
    width: int
    height: int

    @property
    def n_frames(self) -> int:
        return len(self.landmarks)

    @property
    def duration_s(self) -> float:
        return self.n_frames / self.fps if self.fps > 0 else 0.0
