"""The pinned MediaPipe pose model (ADR-006): one file, identified by its SHA-256.

`pose_landmarker_full`, version `float16/1`, is the file MediaPipe's official web sample loads with
@mediapipe/tasks-vision, so the browser and this package can run the same model.

Stdlib only, so the Docker build can run it before dependencies are installed:
    python gaitcore/model.py fetch [DEST]
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

NAME = "pose_landmarker_full"
VERSION = "float16/1"
URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/1/pose_landmarker_full.task"
)
SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"  # pragma: allowlist secret (public file hash)
DEFAULT_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_full.task"
ENV_VAR = "GAITSCAN_POSE_MODEL"


class ModelError(RuntimeError):
    """The pose model file is missing or is not the pinned file."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_path() -> Path:
    """Path of the verified model file ($GAITSCAN_POSE_MODEL or gaitcore/models/)."""
    path = Path(os.environ.get(ENV_VAR) or DEFAULT_PATH)
    if not path.is_file():
        raise ModelError(f"Pose model not found at {path}. Run: python gaitcore/model.py fetch")
    if sha256(path) != SHA256:
        raise ModelError(f"{path} is not the pinned {NAME} {VERSION} model (SHA-256 mismatch).")
    return path


def fetch(dest: Path = DEFAULT_PATH) -> Path:
    """Download the pinned model to `dest`, refusing anything whose hash doesn't match."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(URL, timeout=120) as r, open(tmp, "wb") as f:  # noqa: S310 (fixed https URL)
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if sha256(tmp) != SHA256:
        tmp.unlink()
        raise ModelError(f"Downloaded file does not match the pinned SHA-256 for {NAME} {VERSION}.")
    tmp.replace(dest)
    return dest


if __name__ == "__main__":
    if sys.argv[1:2] != ["fetch"]:
        raise SystemExit("usage: python gaitcore/model.py fetch [DEST]")
    sys.stdout.write(f"{fetch(Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PATH)}\n")
