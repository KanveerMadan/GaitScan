"""The typical curves the result page draws its bands from (Plan V3 Phase 11): GET /references.

Healthy LJMU walkers measured by this app (gaitcore/norms/ljmu_references.json, `make references`):
per joint the mean curve over the gait cycle (heel strike to heel strike, 101 points) and the typical
band, mean +- TYPICAL_SD SDs (as in the verdict). The same for everyone and changed only by a release,
so it's public and cacheable; results don't carry it."""

from typing import Any

from fastapi import APIRouter, Response

from app.core.verdict_copy import COPY
from gaitcore.norms import ljmu_references
from gaitcore.norms.thresholds import TYPICAL_SD

router = APIRouter(tags=["references"])


@router.get("/references")
def references(response: Response) -> dict[str, Any]:
    data = ljmu_references()
    curves = {}
    for joint, c in data["curves"].items():
        curves[joint] = {
            "mean": c["mean"],
            "lo": [round(m - TYPICAL_SD * s, 2) for m, s in zip(c["mean"], c["sd"], strict=True)],
            "hi": [round(m + TYPICAL_SD * s, 2) for m, s in zip(c["mean"], c["sd"], strict=True)],
            "n": c["n"],
        }
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {
        "typical_sd": TYPICAL_SD,
        "curves": curves,
        "gps": {"typical": [0.0, data["gps"]["p95"]]},
        "label": {lang: COPY[lang]["label"]["same_method"] for lang in ("en", "hi")},
        "source": data["source"],
        "pipeline_version": data["pipeline_version"],
    }
