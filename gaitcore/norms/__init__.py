"""References a gait profile is compared with (Plan V3 Phase 11, owner decisions D1, D7, D8).

Cadence: Mobbs L, Fernando V, Fonseka RD, Natarajan P, Maharaj M, Mobbs RJ. Normative Database of
Spatiotemporal Gait Metrics Across Age Groups. Sensors 2025;25(2):581, doi:10.3390/s25020581, CC BY 4.0;
read from the full text (Europe PMC) on 2026-11-12. Mean and SD per 10-year group: Table 4 (females),
Table 5 (males), Table 3 (both); people per group: Table 2. A literature reference: another instrument
(chest-worn IMU), so the thresholds add GaitScan's own error (thresholds.py).

Everything else (step-time variability, knee and hip measures, the GPS): healthy LJMU walkers measured
by this pipeline (Topham et al. 2023, Scientific Data 10:320, CC BY 4.0; ljmu_references.json, built by
`make references` from the participants' anthropometry). A same-method reference already carries the
method's errors, so its thresholds add nothing (D7: "compared with healthy adults measured by this app").

A group is used only with >= MIN_PEOPLE people. Fallbacks, said in the result (D8): no sex given, or too
few people of that sex in the age group -> both sexes of that age ("no_sex"); no age, or an age the
source doesn't cover -> all adults ("all_adults"). Nothing is extrapolated.
"""

import json
import math
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

MIN_PEOPLE = 10
CADENCE_ERROR_95 = 4.5  # steps/min, GaitScan's LJMU accuracy check (gaitcore.accuracy.VALIDATED)

# [lowest age, highest age, label], whole years.
AGE_GROUPS = [
    (18, 20, "18–20"),
    (21, 30, "21–30"),
    (31, 40, "31–40"),
    (41, 50, "41–50"),
    (51, 60, "51–60"),
    (61, 70, "61–70"),
    (71, 80, "71–80"),
]
# Mobbs 2025 cadence, steps/min: (mean, SD, people), in AGE_GROUPS order.
MOBBS_CADENCE = {
    "female": [
        (109.68, 9.95, 11),
        (111.88, 9.25, 43),
        (114.41, 9.45, 34),
        (115.14, 8.75, 26),
        (114.35, 8.36, 18),
        (118.87, 8.21, 11),
        (111.03, 17.04, 3),
    ],
    "male": [
        (103.42, 5.63, 15),
        (105.22, 7.77, 42),
        (109.76, 7.86, 41),
        (109.26, 8.91, 34),
        (107.08, 9.19, 26),
        (110.99, 4.16, 6),
        (111.08, 9.99, 3),
    ],
    # Table 3 (both sexes); people = Table 2's female + male counts per group.
    None: [
        (105.83, 8.02, 26),
        (108.40, 9.17, 85),
        (111.87, 8.86, 75),
        (111.75, 9.24, 60),
        (110.05, 9.47, 44),
        (115.91, 7.85, 17),
        (111.05, 12.49, 6),
    ],
}
WHO = {"female": "women", "male": "men", None: "adults"}


@dataclass(frozen=True)
class Reference:
    mean: float
    sd: float
    n: int  # people
    group: str  # e.g. "women aged 41–50", "all adults"
    source: str  # "mobbs2025" | "ljmu_same_method"
    kind: str  # "literature" | "same_method"
    error_95: float = 0.0  # added to the bands for a literature reference
    fallback: str | None = None  # None | "no_sex" | "all_adults"

    def as_dict(self) -> dict[str, Any]:
        return {
            k: getattr(self, k)
            for k in ("mean", "sd", "n", "group", "source", "kind", "error_95", "fallback")
        }


def _pooled(rows: list[tuple[float, float, int]]) -> tuple[float, float, int]:
    """Mean and SD of groups pooled (the groups' own means and SDs, weighted by their sizes)."""
    n = sum(r[2] for r in rows)
    mean = sum(r[0] * r[2] for r in rows) / n
    ss = sum((r[2] - 1) * r[1] ** 2 + r[2] * (r[0] - mean) ** 2 for r in rows)
    return round(mean, 2), round(math.sqrt(ss / (n - 1)), 2), n


def _age_group(age: float | None) -> int | None:
    if age is None or not math.isfinite(age):
        return None
    return next((i for i, (lo, hi, _) in enumerate(AGE_GROUPS) if lo <= age <= hi), None)


def cadence_reference(sex: str | None, age: float | None) -> Reference:
    g = _age_group(age)
    if g is not None:
        for s in ([sex] if sex else []) + [None]:
            mean, sd, n = MOBBS_CADENCE[s][g]
            if n >= MIN_PEOPLE:
                return Reference(
                    mean,
                    sd,
                    n,
                    f"{WHO[s]} aged {AGE_GROUPS[g][2]}",
                    "mobbs2025",
                    "literature",
                    CADENCE_ERROR_95,
                    None if s == sex and sex else "no_sex",
                )
    mean, sd, n = _pooled(MOBBS_CADENCE[None])  # all adults 18-80, derived from Table 3
    return Reference(mean, sd, n, "all adults", "mobbs2025", "literature", CADENCE_ERROR_95, "all_adults")


@cache
def ljmu_references() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(files("gaitcore.norms").joinpath("ljmu_references.json").read_text())
    return data


# Same-method groups (ljmu_references.json "groups"), most specific first.
def _same_method_groups(sex: str | None, age: float | None) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    if age is not None and math.isfinite(age):
        if 18 <= age <= 40:
            if sex:
                out.append((f"{WHO[sex]} aged 18–40", None))
            out.append(("adults aged 18–40", "no_sex" if sex else None))
        elif 41 <= age <= 65:
            out.append(("adults aged 41–65", "no_sex" if sex else None))
    out.append(("all adults", "all_adults"))
    return out


def same_method_reference(metric: str, sex: str | None, age: float | None) -> Reference | None:
    groups = ljmu_references()["groups"]
    for name, fallback in _same_method_groups(sex, age):
        row = groups.get(name, {}).get(metric)
        if row and row["n"] >= MIN_PEOPLE:
            return Reference(
                row["mean"], row["sd"], row["n"], name, "ljmu_same_method", "same_method", 0.0, fallback
            )
    return None


SOURCES = {
    "mobbs2025": {
        "citation": "Mobbs L, Fernando V, Fonseka RD, Natarajan P, Maharaj M, Mobbs RJ. Normative Database of "
        "Spatiotemporal Gait Metrics Across Age Groups: An Observational Case–Control Study. Sensors 2025;25(2):581.",
        "url": "https://doi.org/10.3390/s25020581",
        "licence": "CC BY 4.0",
    },
    "ljmu_same_method": {
        "citation": "Healthy adults of the LJMU 360 Degree Gait Capture dataset (Topham et al. 2023, Scientific "
        "Data 10:320), measured by this app.",
        "url": "https://doi.org/10.1038/s41597-023-02161-8",
        "licence": "CC BY 4.0",
    },
}


# Error ranges for the joint measures (owner decision, 2026-11-14): no angle reference exists in LJMU, so
# these are the mean absolute errors of a similar method, 2D side-view OpenPose against motion capture
# (Stenum J, Rossi C, Roemmich RT. PLoS Comput Biol 2021;17(4):e1008935, CC BY 4.0, Table 6: hip
# 3.7-4.0, knee 5.1-5.6, ankle 6.3-7.4 deg; the larger is used). Hip carries a note: on LJMU the thigh
# range read 9 deg higher than a thigh-worn sensor on average (r = 0.44; docs/validation/kinematics.md).
ANGLE_ERRORS = {
    "knee": {"mae_deg": 5.6, "source": "stenum2021", "note": None},
    "hip": {"mae_deg": 4.0, "source": "stenum2021", "note": "ljmu_thigh_offset"},
    "ankle": {"mae_deg": 7.4, "source": "stenum2021", "note": None},
}
SOURCES["stenum2021"] = {
    "citation": "Stenum J, Rossi C, Roemmich RT. Two-dimensional video-based analysis of human gait using pose "
    "estimation. PLoS Comput Biol 2021;17(4):e1008935.",
    "url": "https://doi.org/10.1371/journal.pcbi.1008935",
    "licence": "CC BY 4.0",
}
