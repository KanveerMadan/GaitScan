"""PDF report built from a stored v2 result: measurements with units, recording quality, versions.

Deterministic and in memory: the same stored result always gives the same report, and nothing is
written to disk (F15). Every interpolated string is escaped before ReportLab parses its markup (F20).
Plan V3 Phase 3 redesigns this report and adds error ranges.
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

from app.core.copy import DISCLAIMER, NO_ERROR_RANGES
from gaitcore.accuracy import NOT_YET_VALIDATED, accuracy_for

ROWS = (  # (metric key, label); per-leg metrics have "left"/"right"
    ("cadence", "Cadence"),
    ("step_time", "Step time"),
    ("peak_knee_flexion", "Peak knee flexion (per stride)"),
    ("step_length", "Step length (floor calibration)"),
    ("walking_speed", "Walking speed (floor calibration)"),
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
    return f"{item['value']}{sd} {item['unit']} (n = {item['n']})"


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
    story: list[Any] = [
        _p("GaitScan walking measurements", TITLE),
        _p(f"Name: {patient_name or 'Not given'}"),
        _p(f"Recorded: {created_at.strftime('%d %b %Y %H:%M') if created_at else 'unknown'}"),
        Spacer(1, 6),
        _p(DISCLAIMER, SMALL),
        _p("Measurements", H2),
    ]
    rows: list[list[Any]] = [[_p("Measurement"), _p("Left"), _p("Right"), _p("Both legs")]]
    for key, label in ROWS:
        if key not in metrics:
            continue
        m = metrics[key]
        name: list[Any] = [_p(label)]
        if accuracy.get(key, {}).get("status") == NOT_YET_VALIDATED:
            name.append(_p("Not yet validated", SMALL))
        if isinstance(m, dict) and ("left" in m or "right" in m):
            rows.append([name, _p(_fmt(m.get("left"))), _p(_fmt(m.get("right"))), _p("")])
        else:
            rows.append([name, _p(""), _p(""), _p(_fmt(m))])
    story += [_table(rows, [6 * cm, 3.7 * cm, 3.7 * cm, 3.7 * cm]), Spacer(1, 4)]
    story += [_p(note) for note in result.get("notes") or []]
    story += [
        _p(f"{label}: {accuracy[key]['note']}", SMALL)
        for key, label in ROWS
        if key in metrics and key in accuracy and accuracy[key].get("status") == NOT_YET_VALIDATED
    ]
    story.append(_p(NO_ERROR_RANGES, SMALL))
    if "step_length" not in metrics:
        story.append(
            _p("Step length and walking speed need a floor calibration and were not measured.", SMALL)
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
