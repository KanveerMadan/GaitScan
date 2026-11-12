"""PDF report built from a stored v2 result: measurements with units, recording quality, versions.

Deterministic and in memory: the same stored result always gives the same report, and nothing is
written to disk (F15). Every interpolated string is escaped before ReportLab parses its markup (F20).
Error ranges come from the result's accuracy block (gaitcore/accuracy.py).
"""

import io
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.copy import DISCLAIMER, ERROR_RANGES
from gaitcore.accuracy import NOT_YET_VALIDATED, accuracy_for

WALK_ROWS = (  # (metric key, label); per-leg metrics have "left"/"right"
    ("cadence", "Cadence"),
    ("step_time", "Step time"),
    ("peak_knee_flexion", "Peak knee flexion (per stride)"),
    ("step_length", "Step length (floor calibration)"),
    ("walking_speed", "Walking speed (floor calibration)"),
)
TREADMILL_ROWS = (  # a treadmill has no floor calibration; step length comes from the entered belt speed
    ("cadence", "Cadence"),
    ("step_time", "Step time"),
    ("peak_knee_flexion", "Peak knee flexion (per stride)"),
    ("belt_speed", "Belt speed (entered)"),
    ("step_length", "Step length (from the belt speed)"),
)

TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13)
SMALL = ParagraphStyle(
    "small", fontName="Helvetica", fontSize=8, leading=10.5, textColor=colors.HexColor("#475569")
)


def _p(text: object, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _fmt(item: dict[str, Any] | None) -> str:
    if not item or item.get("value") is None:
        return "not measured"
    sd = f" ± {item['sd']} SD" if item.get("sd") is not None else ""
    n = f" (n = {item['n']})" if "n" in item else ""  # an entered value (belt speed) has no count
    return f"{item['value']}{sd} {item['unit']}{n}"


def _accuracy(a: dict[str, Any] | None) -> str:
    if not a:
        return "-"
    if a.get("status") == NOT_YET_VALIDATED:
        return "Not yet validated"
    return f"± {a['error_95']} {a['unit']}"


def _table(rows: list[list[Any]], widths: list[float]) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def build_pdf(result: dict[str, Any], patient_name: str | None, created_at: datetime | None) -> bytes:
    metrics: dict[str, Any] = result.get("metrics", {})
    # Results stored before the accuracy block existed get today's labels.
    accuracy: dict[str, Any] = result.get("accuracy") or accuracy_for(metrics)
    quality: dict[str, Any] = result.get("quality", {})
    model: dict[str, str] = result.get("model", {})
    treadmill = result.get("test") == "treadmill"
    shown = TREADMILL_ROWS if treadmill else WALK_ROWS
    story: list[Any] = [
        _p("GaitScan walking measurements" + (": treadmill" if treadmill else ""), TITLE),
        _p("Test: Treadmill walk" if treadmill else "Test: Walk across the floor"),
        _p(f"Name: {patient_name or 'Not given'}"),
        _p(f"Recorded: {created_at.strftime('%d %b %Y %H:%M') if created_at else 'unknown'}"),
        Spacer(1, 6),
        _p(DISCLAIMER, SMALL),
        _p("Measurements", H2),
    ]
    rows: list[list[Any]] = [[_p("Measurement"), _p("Left"), _p("Right"), _p("Both legs"), _p("Error range")]]
    for key, label in shown:
        if key not in metrics:
            continue
        m = metrics[key]
        acc = _p(_accuracy(accuracy.get(key)), SMALL)
        if isinstance(m, dict) and ("left" in m or "right" in m):
            rows.append([_p(label), _p(_fmt(m.get("left"))), _p(_fmt(m.get("right"))), _p(""), acc])
        else:
            rows.append([_p(label), _p(""), _p(""), _p(_fmt(m)), acc])
    story += [_table(rows, [4.4 * cm, 3.2 * cm, 3.2 * cm, 3.4 * cm, 2.9 * cm]), Spacer(1, 4)]
    story += [_p(note) for note in result.get("notes") or []]
    story += [
        _p(f"{label}: {accuracy[key]['note']}", SMALL)
        for key, label in shown
        if key in metrics and key in accuracy and accuracy[key].get("status") == NOT_YET_VALIDATED
    ]
    story.append(_p(ERROR_RANGES, SMALL))
    if "step_length" not in metrics and not treadmill:
        story.append(
            _p("Step length and walking speed need a floor calibration and were not measured.", SMALL)
        )

    passes: list[dict[str, Any]] = result.get("passes") or []
    if passes:
        story.append(_p("Each pass", H2))
        p_rows: list[list[Any]] = [[_p("Pass"), _p("Direction"), _p("Steps"), _p("Cadence"), _p("Step time")]]
        for p in passes:
            p_rows.append(
                [
                    _p(p["pass"]),
                    _p(str(p["direction"]).replace("_", " ")),
                    _p(p["steps"]),
                    _p(_fmt({**p["cadence"], "n": p["steps"]})),
                    _p(_fmt(p["step_time"])),
                ]
            )
        story.append(_table(p_rows, [1.5 * cm, 3 * cm, 1.6 * cm, 5.5 * cm, 5.5 * cm]))
        v = result.get("pass_variability")
        if v:
            story.append(
                _p(
                    f"Spread between passes (SD): cadence {v['cadence_sd']['value']} steps/min, "
                    f"step time {v['step_time_sd']['value']} s.",
                    SMALL,
                )
            )

    strides = quality.get("strides") or {}
    usable = quality.get("usable_frame_fraction")
    q_rows = [
        ["Steady walking analysed", f"{quality.get('steady_walking_s')} s in {quality.get('passes')} passes"],
        [
            "Frames used",
            f"{round(usable * 100)}% of {quality.get('frames_total')}" if usable is not None else "-",
        ],
        [
            "Steps / strides detected",
            f"{quality.get('steps_detected')} steps; strides left {strides.get('left')}, right {strides.get('right')}",
        ],
        ["Frame rate", f"{quality.get('fps')} fps"],
        ["Floor calibration", "yes" if quality.get("calibrated") else "no"],
    ]
    story += [
        _p("Recording quality", H2),
        _table([[_p("Check"), _p("Value")], *[[_p(a), _p(b)] for a, b in q_rows]], [6 * cm, 11.1 * cm]),
        Spacer(1, 10),
        _p(
            f"Pipeline {result.get('pipeline_version')} · pose model {model.get('name')} {model.get('version')} "
            f"(MediaPipe {model.get('mediapipe')}, SHA-256 {str(model.get('sha256', ''))[:12]}…)",
            SMALL,
        ),
    ]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm).build(
        story
    )
    return buf.getvalue()
