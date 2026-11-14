"""Same-method references from healthy LJMU walkers (Plan V3 Phase 11, BE-B, owner decision D7):
`make references` -> gaitcore/norms/ljmu_references.json.

Data: LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0): the side-view
clips in ljmu_reference.csv, and Participant_Anthropometry.xlsx for sex and age (fetched by
`python -m evaluation.fetch_ljmu --meta`). Every participant is a healthy adult, 18-65.

Per participant, the median of their clips' values (several clips = a longer recording, as the app asks
for: walk across and back); then per group (all adults; adults, women and men aged 18-40; adults aged
41-65) the mean and SD of the participants' values, kept only with >= 10 participants
(gaitcore.norms.MIN_PEOPLE). Curves: the mean and SD of the participants' mean curves. GPS band: each
participant's GPS against the others' mean curves (leave-one-out).

Release gate (D1): each participant judged against references built without them (cadence: Mobbs 2025,
by their sex and age), counted: share "outside" (gate <= 5%) and "keep_an_eye" (<= 25%).
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np

from evaluation.evaluate import load_clip, load_reference
from gaitcore import __version__
from gaitcore.norms import MIN_PEOPLE, Reference, cadence_reference
from gaitcore.pipeline import analyse
from gaitcore.profile import KINEMATICS
from gaitcore.verdict import JOINTS, assess, gps

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gaitcore", "norms", "ljmu_references.json"
)
METRICS = ("step_time_cv", "stance_pct", "swing_pct", "double_support_pct", *KINEMATICS)
TIMING = ("cadence", "step_time_cv", "stance_pct", "swing_pct", "double_support_pct")


def anthropometry(path: str) -> dict[int, tuple[str | None, float | None]]:
    import openpyxl  # type: ignore[import-untyped]  # only for building the references

    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    out = {}
    for row in list(ws.iter_rows(values_only=True))[1:]:
        if not isinstance(row[0], (int, float)):
            continue
        sex = {"F": "female", "M": "male"}.get(str(row[3]).strip())
        age = float(row[4]) if isinstance(row[4], (int, float)) else None
        out[int(row[0])] = (sex, age)
    return out


def group_names(sex: str | None, age: float | None) -> list[str]:
    names = ["all adults"]
    if age is not None and 18 <= age <= 40:
        names.append("adults aged 18–40")
        if sex:
            names.append(f"{'women' if sex == 'female' else 'men'} aged 18–40")
    elif age is not None and 41 <= age <= 65:
        names.append("adults aged 41–65")
    return names


def participant_profiles(landmark_dirs: list[str]) -> dict[int, dict[str, Any]]:
    clips: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ref in load_reference():
        clip = load_clip(ref.clip, landmark_dirs, None)
        if clip is None:
            continue
        p = analyse(clip).to_dict().get("gait_profile")
        if p:
            clips[ref.participant].append(p)
    out = {}
    for pid, ps in clips.items():

        def med(metric: str, ps: list[dict[str, Any]] = ps) -> float | None:
            part = "timing" if metric in TIMING else "kinematics"
            v = [p[part][metric]["value"] for p in ps if p[part][metric]["value"] is not None]
            return float(np.median(v)) if v else None

        def n_sum(metric: str, ps: list[dict[str, Any]] = ps) -> int:
            part = "timing" if metric in TIMING else "kinematics"
            return int(sum(p[part][metric]["n"] or 0 for p in ps))

        curves = {}
        for j in JOINTS:
            cs = [p["kinematics"]["curves"][j]["mean"] for p in ps if p["kinematics"]["curves"].get(j)]
            curves[j] = {"mean": np.mean(cs, axis=0).tolist()} if cs else None
        out[pid] = {
            "clips": len(ps),
            "timing": {m: {"value": med(m), "n": n_sum(m)} for m in TIMING},
            "kinematics": {**{m: {"value": med(m), "n": n_sum(m)} for m in KINEMATICS}, "curves": curves},
            "quality": {
                "steps": int(sum(p["quality"]["steps"] for p in ps)),
                "usable_frame_fraction": float(np.mean([p["quality"]["usable_frame_fraction"] for p in ps])),
                "leg_visibility": float(np.mean([p["quality"]["leg_visibility"] for p in ps])),
            },
        }
    return out


def _value(p: dict[str, Any], metric: str) -> float | None:
    v: float | None = p["timing" if metric in TIMING else "kinematics"][metric]["value"]
    return v


def groups(
    profiles: dict[int, dict[str, Any]], meta: dict[int, tuple[str | None, float | None]]
) -> dict[str, Any]:
    members: dict[str, list[int]] = defaultdict(list)
    for pid in profiles:
        for g in group_names(*meta.get(pid, (None, None))):
            members[g].append(pid)
    out: dict[str, Any] = {}
    for g, pids in members.items():
        rows = {}
        for m in METRICS:
            v = [x for pid in pids if (x := _value(profiles[pid], m)) is not None]
            if len(v) >= MIN_PEOPLE:
                rows[m] = {
                    "mean": round(float(np.mean(v)), 2),
                    "sd": round(float(np.std(v, ddof=1)), 2),
                    "n": len(v),
                }
        if rows:
            out[g] = rows
    return out


def mean_curves(profiles: dict[int, dict[str, Any]], skip: int | None = None) -> dict[str, Any]:
    out = {}
    for j in JOINTS:
        cs = [
            p["kinematics"]["curves"][j]["mean"]
            for pid, p in profiles.items()
            if pid != skip and p["kinematics"]["curves"][j]
        ]
        out[j] = {
            "mean": [round(v, 2) for v in np.mean(cs, axis=0)],
            "sd": [round(v, 2) for v in np.std(cs, axis=0, ddof=1)],
            "n": len(cs),
        }
    return out


def release_gate(
    profiles: dict[int, dict[str, Any]], meta: dict[int, tuple[str | None, float | None]]
) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    drivers: dict[str, int] = defaultdict(int)
    for pid, p in profiles.items():
        others = {k: v for k, v in profiles.items() if k != pid}
        table = groups(others, meta)
        sex, age = meta.get(pid, (None, None))

        def refs(
            metric: str, s: str | None, a: float | None, table: dict[str, Any] = table
        ) -> Reference | None:
            if metric == "cadence":
                return cadence_reference(s, a)
            for g in reversed(group_names(s, a)):  # most specific first
                row = table.get(g, {}).get(metric)
                if row and row["n"] >= MIN_PEOPLE:
                    return Reference(row["mean"], row["sd"], row["n"], g, "ljmu_same_method", "same_method")
            return None

        v = assess(p, (sex, age), refs)
        counts[v["overall"] or f"no_verdict:{v['no_verdict']}"] += 1
        for d in v["drivers"]:
            drivers[d] += 1
    judged = sum(counts[k] for k in ("typical", "keep_an_eye", "outside"))
    share = {
        k: round(counts[k] / judged, 3) if judged else None for k in ("typical", "keep_an_eye", "outside")
    }
    return {
        "participants": len(profiles),
        "judged": judged,
        "counts": dict(counts),
        "share": share,
        "drivers": dict(drivers),
        "passes": bool(judged and (share["outside"] or 0) <= 0.05 and (share["keep_an_eye"] or 0) <= 0.25),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--landmarks", nargs="+", required=True)
    p.add_argument("--meta", default="data/ljmu/Participant_Anthropometry.xlsx")
    p.add_argument("--out", default=OUT)
    args = p.parse_args()
    meta = anthropometry(args.meta)
    profiles = participant_profiles(args.landmarks)
    table = groups(profiles, meta)
    gps_values = []
    for pid, prof in profiles.items():
        g = gps(prof["kinematics"]["curves"], mean_curves(profiles, skip=pid))
        if g:
            gps_values.append(g["value"])
    data = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "pipeline_version": __version__,
        "source": "LJMU 360 Degree Gait Capture (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0); side-view clips in evaluation/ljmu_reference.csv",
        "participants": len(profiles),
        "clips": int(sum(x["clips"] for x in profiles.values())),
        "groups": table,
        "curves": mean_curves(profiles),
        "gps": {
            "mean": round(float(np.mean(gps_values)), 2),
            "sd": round(float(np.std(gps_values, ddof=1)), 2),
            "p95": round(float(np.percentile(gps_values, 95)), 2),
            "n": len(gps_values),
        },
        "release_gate": release_gate(profiles, meta),
    }
    with open(args.out, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(
        json.dumps(
            {k: v for k, v in data.items() if k not in ("curves", "groups")}, indent=1, ensure_ascii=False
        )
    )
    print("groups:", {g: len(r) for g, r in table.items()})


if __name__ == "__main__":
    main()
