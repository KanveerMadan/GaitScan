"""Download the LJMU side-view clips that ljmu_reference.csv lists (Topham et al. 2023, CC BY 4.0), or with
--imu the right-thigh goniometer files of tasks 1-2.

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


SENSOR = re.compile(r"Participant_\d+/Experiment_[12]/E[12]T[12]/P\d+_E[12]T[12]\.csv")


def fetch_sensor(out: str) -> None:
    """The right-thigh goniometer files of tasks 1 and 2 (experiments 1 and 2) for every participant
    who wore it, saved as <out>/P<p>_E<e>T<t>.csv (about 100 KB each; evaluation/leg_labels.py)."""
    os.makedirs(out, exist_ok=True)
    with RemoteZip(URL) as z:
        for m in sorted(n for n in z.namelist() if SENSOR.fullmatch(n)):
            dest = os.path.join(out, m.rsplit("/", 1)[1])
            if not os.path.exists(dest):
                with z.open(m) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print("ok", m, flush=True)


def fetch_meta(out: str) -> None:
    """The participants' sex, age and height (Participant_Anthropometry.xlsx), for the same-method
    references (evaluation/references.py)."""
    os.makedirs(out, exist_ok=True)
    with RemoteZip(URL) as z:
        name = next(n for n in z.namelist() if n.endswith("Participant_Anthropometry.xlsx"))
        with z.open(name) as src, open(os.path.join(out, "Participant_Anthropometry.xlsx"), "wb") as dst:
            shutil.copyfileobj(src, dst)
    print("ok", name)


def main(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    todo = [r.clip for r in load_reference() if not os.path.exists(os.path.join(out, f"{r.clip}.mp4"))]
    with RemoteZip(URL) as z:
        for clip in todo:
            with z.open(member(clip)) as src, open(os.path.join(out, f"{clip}.mp4"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            print("ok", clip, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--imu":
        fetch_sensor(sys.argv[2])
    elif sys.argv[1] == "--meta":
        fetch_meta(sys.argv[2])
    else:
        main(sys.argv[1])
