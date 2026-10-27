"""Download the LJMU side-view clips that ljmu_reference.csv lists (Topham et al. 2023, CC BY 4.0).

Reads only those members of the 19 GB dataset zip, with HTTP range requests, and saves them as
<out>/<clip>.mp4. Needs remotezip and zipfile-deflate64 (`make fetch-ljmu` adds them for the run).
"""

import os
import re
import shutil
import sys

import zipfile_deflate64  # noqa: F401  (registers Deflate64, which the dataset zip uses)
from remotezip import RemoteZip

from evaluation.evaluate import load_reference

URL = "https://opendata.ljmu.ac.uk/id/eprint/133/3/Gait%20Dataset.zip"


def member(clip: str) -> str:
    m = re.fullmatch(r"P(\d+)_E(\d)T(\d)_90", clip)
    if not m:
        raise ValueError(clip)
    p, e, t = m.groups()
    return f"Participant_{p}/Experiment_{e}/E{e}T{t}/{clip}.mp4"


def main(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    todo = [r.clip for r in load_reference() if not os.path.exists(os.path.join(out, f"{r.clip}.mp4"))]
    with RemoteZip(URL) as z:
        for clip in todo:
            with z.open(member(clip)) as src, open(os.path.join(out, f"{clip}.mp4"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            print("ok", clip, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
