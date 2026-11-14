"""Adds the verdict to a stored gait profile when a result is read (Plan V3 Phase 11, BE-B).

The verdict depends on the person's current sex and birth year (settings, or the profile of the person
measured), so it's worked out on every read and never stored: changing them in Settings changes the
comparison, and no stored result is rewritten. Shared links get no person (all adults), so they reveal
no age or sex. Pelvis oscillation stays in the stored profile ("hidden") and isn't returned.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import object_session

from app.core.verdict_copy import COPY
from app.db.models import Profile, User
from gaitcore.verdict import assess

Person = tuple[str | None, float | None] | None
LANGS = ("en", "hi")


def person_for(db: DBSession | None, user_id: int | None, profile_id: int | None, year: int | None) -> Person:
    if db is None:
        return None
    sex, born = None, None
    if profile_id is not None:
        p = db.get(Profile, profile_id)
        if p is not None:
            sex, born = p.sex, p.birth_year
    elif user_id is not None:
        u = db.get(User, user_id)
        s = (u.settings or {}) if u is not None else {}
        sex, born = s.get("sex"), s.get("birth_year")
    age = (year or date.today().year) - born if born else None
    return sex, (float(age) if age is not None else None)


def person_for_session(s: Any) -> Person:
    year = s.created_at.year if getattr(s, "created_at", None) else None
    return person_for(object_session(s), s.user_id, s.profile_id, year)


def _both(pick: Any) -> dict[str, Any]:
    return {lang: pick(COPY[lang]) for lang in LANGS}


def _fmt(v: float | None) -> str:
    """As the app and the PDF write numbers: whole numbers from 100 up, else one decimal. Fewer digits
    hid differences: 44.8 below a range from 45.3 read "45 (typical 45–71)"."""
    if v is None:
        return "–"
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}"


def _with_unit(text: str, unit: str) -> str:
    return f"{text}{unit}" if unit in ("°", "%") else f"{text} {unit}"


def present(result: dict[str, Any] | None, person: Person) -> dict[str, Any] | None:
    if not result or not result.get("gait_profile"):
        return None if result is None else {**result, "gait_profile": None}
    gp = {k: v for k, v in result["gait_profile"].items() if k != "hidden"}
    v = assess(gp, person)
    metrics = {}
    for m, row in v["metrics"].items():
        ref = row["reference"]
        if ref is not None:
            kind = "literature" if ref["kind"] == "literature" else "same_method"
            ref = {**ref, "label": _both(lambda c, k=kind: c["label"][k])}
        err = row.get("error")
        if err is not None:
            err = {
                **err,
                "text": _both(lambda c, e=err: c["error"].format(mae=e["mae_deg"])),
                "note_text": None if not err["note"] else _both(lambda c, e=err: c["error_note"][e["note"]]),
            }
        metrics[m] = {**row, "reference": ref, "error": err, "name": _both(lambda c, m=m: c["metric"][m])}
    observations = []
    for m in v["drivers"]:
        row = metrics[m]
        unit = (gp.get("timing", {}).get(m) or gp.get("kinematics", {}).get(m) or {}).get("unit", "")
        lo, hi = row["typical"]
        observations.append(
            {
                "metric": m,
                "level": row["level"],
                "text": _both(
                    lambda c, m=m, row=row, unit=unit, lo=lo, hi=hi: c["finding"].format(
                        metric=c["metric"][m],
                        direction=c["direction"][row["direction"] or "above"],
                        value=_with_unit(_fmt(row["value"]), c["unit"].get(unit, unit)),
                        lo=_fmt(lo),
                        hi=_with_unit(_fmt(hi), c["unit"].get(unit, unit)),
                    )
                ),
            }
        )
    overall = v["overall"]
    verdict = {
        "overall": overall,
        "no_verdict": v["no_verdict"],
        "headline": None if overall is None else _both(lambda c: c["headline"][overall]),
        "summary": _both(lambda c: c["overall"][overall] if overall else c["no_verdict"][v["no_verdict"]]),
        "observations": observations,
        "drivers": v["drivers"],
        "next_steps": _both(lambda c: [c["next_steps"][overall]] if overall else []),
        "tips": _both(lambda c: [c["tips"][t] for t in v["tips"]]),
        "notes": _both(lambda c: [c["fallback"][f] for f in v["fallbacks"]]),
        "notice": _both(lambda c: c["notice"]),
        "disclaimer": _both(lambda c: c["disclaimer"]),
        "metrics": metrics,
        "gps": None if v["gps"] is None else {**v["gps"], "label": _both(lambda c: c["label"]["gps"])},
    }
    return {**result, "gait_profile": {**gp, "verdict": verdict}}
