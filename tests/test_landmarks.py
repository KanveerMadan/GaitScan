"""Counting people per frame (gaitcore.landmarks). MediaPipe sometimes returns the walker twice: a
second, partial skeleton inside the first one's box. On LJMU (Topham et al. 2023, CC BY 4.0) that
duplicate flagged empty-room clips as `multiple_people`; a real second person must still count.
"""

from types import SimpleNamespace

import cv2
import numpy as np

import gaitcore.landmarks as L

HIPS = (23, 24)


def pose(x0, y0, x1, y1, hip=None):
    """33 landmarks spread over the box (x0, y0)-(x1, y1); both hips at `hip` (default: box centre)."""
    xs, ys = np.linspace(x0, x1, 33), np.linspace(y0, y1, 33)
    hx, hy = hip or ((x0 + x1) / 2, (y0 + y1) / 2)
    return [
        SimpleNamespace(x=hx if i in HIPS else xs[i], y=hy if i in HIPS else ys[i], z=0.0, visibility=0.9)
        for i in range(33)
    ]


WALKER = pose(0.40, 0.20, 0.60, 0.90)


def test_no_pose_and_one_pose():
    assert L.count_people([]) == 0
    assert L.count_people([WALKER]) == 1


def test_a_second_skeleton_inside_the_walker_counts_once():
    assert L.count_people([WALKER, pose(0.45, 0.30, 0.55, 0.80)]) == 1
    # a partial duplicate that sticks out of the box still has its hips on the walker
    assert L.count_people([WALKER, pose(0.50, 0.40, 0.75, 0.95, hip=(0.55, 0.55))]) == 1


def test_a_second_person_beside_the_walker_counts_twice():
    assert L.count_people([WALKER, pose(0.70, 0.25, 0.85, 0.95)]) == 2


def test_an_overlapping_person_whose_hips_are_outside_the_walker_counts_twice():
    assert L.count_people([WALKER, pose(0.55, 0.20, 0.80, 0.90, hip=(0.70, 0.55))]) == 2


def test_extract_clip_counts_a_duplicate_detection_as_one_person(tmp_path, monkeypatch):
    path = str(tmp_path / "clip.avi")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (64, 48))
    for _ in range(4):
        out.write(np.zeros((48, 64, 3), np.uint8))
    out.release()
    frames = [[WALKER, pose(0.45, 0.30, 0.55, 0.80)], [WALKER, pose(0.70, 0.25, 0.85, 0.95)], [WALKER], []]

    class FakeLandmarker:
        def __init__(self):
            self.i = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def detect_for_video(self, image, ts):
            self.i += 1
            return SimpleNamespace(pose_landmarks=frames[self.i - 1])

    monkeypatch.setattr(L, "_options", lambda: SimpleNamespace(num_poses=1))
    monkeypatch.setattr(L.PoseLandmarker, "create_from_options", staticmethod(lambda o: FakeLandmarker()))
    clip = L.extract_clip(path)
    assert clip.landmarks["n_poses"].tolist() == [1, 2, 1, 0]
    assert clip.landmarks["lm0_x"].notna().tolist() == [True, True, True, False]
