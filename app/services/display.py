"""Display wording for stored sessions.

Rows written before Phase 0 carry diagnostic / injury wording in their stored
text (labels, finding sentences, LLM "why" lines). Summary labels are always
recomputed from the stored score; free text is replaced when it matches the
legacy vocabulary below.

ponytail: regex filter over stored text. Delete once pre-Phase-0 rows are purged
or re-analysed (Phase 2 re-baselines results with a pipeline_version).
"""

import re

from gaitcore.legacy import summary_for_score

LEGACY_WORDING = re.compile(
    r"abnormal|injur|damage|prescri|diagnos|risk|\blimp|affected|\bpain\b|shin splint|"
    r"compensat|doctor|serious|healthy|fall",
    re.I,
)
ACTIVITY_NAMES = {"Limping": "Asymmetric Walking"}
METRIC_NAMES = {"Affected Side": "Less-moving Side"}


def activity(name):
    return ACTIVITY_NAMES.get(name, name)


def text(stored, fallback):
    return fallback if stored and LEGACY_WORDING.search(stored) else stored


def summary(score):
    label, meaning, colour = summary_for_score(score)
    return {"risk_label": label, "risk_meaning": meaning, "risk_color": colour}


def finding(f):
    metric = METRIC_NAMES.get(f.metric, f.metric)
    return {
        "metric": metric,
        "value": f.value,
        "status": f.status,
        "plain_english": text(f.plain_english, f"{metric}: {f.value}."),
    }


def exercise(ex):
    return {
        "name": ex.name,
        "muscle": ex.muscle,
        "difficulty": ex.difficulty,
        "instructions": ex.instructions,
        "why": text(ex.why, "General exercise matched to the measurements above."),
    }
