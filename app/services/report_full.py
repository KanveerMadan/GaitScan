"""The full report for a v3 result (Plan V3 Phase 11, BE-C; design note §8 and the owner's brief):
summary, timing and rhythm, joint movement, progress (only with earlier sessions), recording quality and
method. English or Hindi.

- Both legs pooled; no per-side values and so no symmetry page (decision A). Pelvis oscillation is
  never shown (it's stored under "hidden", which app.services.gait_profile.present drops).
- Words come from app/core/verdict_copy.py (the verdict, shared with the app) and app/core/report_copy.py.
- Fonts: Noto Sans and Noto Sans Devanagari (SIL OFL 1.1, app/assets/fonts), registered once. Noto Sans
  Devanagari has no Latin letters, so in Hindi every run of characters it lacks is set in Noto Sans;
  Devanagari is shaped by uharfbuzz.
- Charts are vector drawings (reportlab.graphics). Levels use a shape as well as a colour (circle,
  triangle, square), and the verdict box a border style (single, dashed, double), so the report reads in
  black and white.
- Deterministic and in memory (F15): built twice (the first pass counts the pages for "Page n of N"),
  nothing written to disk. Every interpolated string is escaped before ReportLab parses markup (F20).
"""

import functools
import io
import os
import re
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, PolyLine, String
from reportlab.graphics.shapes import Rect as _Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.report_copy import REPORT
from app.core.verdict_copy import COPY
from app.services.gait_profile import Person, present
from gaitcore.norms import ljmu_references
from gaitcore.norms.thresholds import TYPICAL_SD

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
FACES = {
    "NotoSans": "NotoSans-Regular.ttf",
    "NotoSans-Bold": "NotoSans-Bold.ttf",
    "NotoSansDevanagari": "NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Bold": "NotoSansDevanagari-Bold.ttf",
}
Rect: Any = _Rect  # the stubs type Rect's style keywords narrower than ReportLab accepts
DEVANAGARI = re.compile("[\u0900-\u097f\ua8e0-\ua8ff]")
DANDA_AFTER_LATIN = re.compile("([^\\s\u0900-\u097f])([\u0964\u0965])")
BASE = {"en": ("NotoSans", "NotoSans-Bold"), "hi": ("NotoSansDevanagari", "NotoSansDevanagari-Bold")}
WIDTH = A4[0] - 4 * cm  # 17 cm of text

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
RULE = colors.HexColor("#cbd5e1")
HEAD_BG = colors.HexColor("#eef2f7")
LEVEL_COLOUR = {
    "typical": colors.HexColor("#15803d"),
    "slightly_outside": colors.HexColor("#b45309"),
    "clearly_outside": colors.HexColor("#b91c1c"),
}
OVERALL_COLOUR = {
    "typical": LEVEL_COLOUR["typical"],
    "keep_an_eye": LEVEL_COLOUR["slightly_outside"],
    "outside": LEVEL_COLOUR["clearly_outside"],
    None: MUTED,
}
OVERALL_TINT = {
    "typical": colors.HexColor("#f0fdf4"),
    "keep_an_eye": colors.HexColor("#fffbeb"),
    "outside": colors.HexColor("#fef2f2"),
    None: colors.HexColor("#f8fafc"),
}
TIMING_ROWS = ("cadence", "step_time", "step_time_cv", "stance_pct", "swing_pct", "double_support_pct")
EVENT_ROWS = ("knee_ic", "knee_peak_swing", "hip_peak_ext", "hip_peak_flex", "ankle_ic")
ROM_ROWS = ("knee_rom", "hip_rom", "ankle_rom")
POSTURE_ROWS = ("trunk_lean_deg", "arm_swing_deg")
# A change smaller than this between two tests shows as "no change": the error range where one is
# known (cadence: LJMU; knee and hip: Stenum 2021), else a round figure.
SAME = {"cadence": 4.5, "step_time_cv": 1.0, "knee_rom": 5.6, "hip_rom": 4.0, "gps": 1.0}
PROGRESS = ("cadence", "step_time_cv", "knee_rom", "hip_rom", "gps")


def hindi_words(text: str) -> list[tuple[str, bool]]:
    """Hindi text as (word or whitespace, set in Noto Sans Devanagari?). ReportLab shapes a whole word
    with the font of its first character, so each word gets one face: Devanagari if it has any
    Devanagari, else Noto Sans. A danda after Latin text ("LJMU)।") gets a space so it's a word of its
    own."""
    text = DANDA_AFTER_LATIN.sub(r"\1 \2", text)
    return [(t, t.isspace() or bool(DEVANAGARI.search(t))) for t in re.split(r"(\s+)", text) if t]


@functools.cache
def _register() -> dict[str, frozenset[int]]:
    """Register the fonts once per process; returns the characters each face can draw (tests check
    that every Hindi word is drawable in the face it's set in)."""
    cmaps = {}
    for name, file in FACES.items():
        font = TTFont(name, os.path.join(FONT_DIR, file))
        pdfmetrics.registerFont(font)
        cmaps[name] = frozenset(font.face.charToGlyph)
    pdfmetrics.registerFontFamily("NotoSans", normal="NotoSans", bold="NotoSans-Bold")
    pdfmetrics.registerFontFamily(
        "NotoSansDevanagari", normal="NotoSansDevanagari", bold="NotoSansDevanagari-Bold"
    )
    return cmaps


class Writer:
    """Styles and text for one language."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.r = REPORT[lang]
        self.c = COPY[lang]
        self.cmaps = _register()
        self.font, self.bold = BASE[lang]

        def style(name: str, size: float, bold: bool = False, colour: Any = INK, **kw: Any) -> ParagraphStyle:
            return ParagraphStyle(
                name, fontName=self.bold if bold else self.font, fontSize=size, leading=size * 1.38,
                textColor=colour, shaping=1 if self.lang == "hi" else 0, **kw,
            )  # fmt: skip

        self.title = style("title", 17, True, spaceAfter=2)
        self.h2 = style("h2", 12.5, True, spaceBefore=4, spaceAfter=6)
        self.h3 = style("h3", 10.5, True, spaceBefore=8, spaceAfter=3)
        self.body = style("body", 9.3)
        self.cell = style("cell", 8.6)
        self.cell_bold = style("cellb", 8.6, True)
        self.small = style("small", 7.8, colour=MUTED)
        self.big = style("big", 14, True)
        self.header = style("header", 7.8, colour=MUTED)

    def markup(self, text: object, bold: bool = False) -> str:
        """Escaped text; in Hindi, each word in the face hindi_words picks for it."""
        if self.lang == "en":
            return escape(str(text))
        latin = "NotoSans-Bold" if bold else "NotoSans"
        return "".join(
            escape(word) if deva else f'<font name="{latin}">{escape(word)}</font>'
            for word, deva in hindi_words(str(text))
        )

    def p(self, text: object, style: ParagraphStyle | None = None) -> Paragraph:
        style = style or self.body
        return Paragraph(self.markup(text, bold=style.fontName == self.bold), style)

    def num(self, v: float | None, digits: int | None = None) -> str:
        if v is None:
            return "–"
        if digits is None:
            digits = 0 if abs(v) >= 100 else 1
        return f"{v:.{digits}f}".replace("-", "\u2212")  # a real minus sign

    def unit(self, u: str) -> str:
        return {"deg": "°"}.get(u, self.c["unit"].get(u, u))

    def with_unit(self, v: float | None, u: str, digits: int | None = None) -> str:
        if v is None:
            return self.r["not_measured"]
        unit = self.unit(u)
        return f"{self.num(v, digits)}{unit}" if unit == "°" else f"{self.num(v, digits)} {unit}"


# ---- small drawings -------------------------------------------------------------------------------
def level_mark(level: str | None, size: float = 8) -> Drawing:
    """A shape as well as a colour: circle = typical, triangle = slightly outside, square = outside."""
    d = Drawing(size, size, initialFontName="NotoSans")
    colour = LEVEL_COLOUR.get(level or "", MUTED)
    if level == "typical":
        d.add(Circle(size / 2, size / 2, size / 2 - 0.5, fillColor=colour, strokeColor=colour))
    elif level == "slightly_outside":
        d.add(
            Polygon([0.3, 0.5, size - 0.3, 0.5, size / 2, size - 0.3], fillColor=colour, strokeColor=colour)
        )
    elif level == "clearly_outside":
        d.add(Rect(0.5, 0.5, size - 1, size - 1, fillColor=colour, strokeColor=colour))
    return d


def overall_icon(overall: str | None, size: float = 34) -> Drawing:
    d = Drawing(size, size, initialFontName="NotoSans")
    colour = OVERALL_COLOUR[overall]
    white = colors.white
    s = size
    if overall == "typical":  # circle with a tick
        d.add(Circle(s / 2, s / 2, s / 2 - 1, fillColor=colour, strokeColor=colour))
        d.add(
            PolyLine(
                [s * 0.28, s * 0.52, s * 0.44, s * 0.36, s * 0.73, s * 0.66], strokeColor=white, strokeWidth=3
            )
        )
    elif overall == "keep_an_eye":  # triangle with an exclamation mark
        d.add(Polygon([1, 2, s - 1, 2, s / 2, s - 1], fillColor=colour, strokeColor=colour))
        d.add(Line(s / 2, s * 0.36, s / 2, s * 0.68, strokeColor=white, strokeWidth=3))
        d.add(Circle(s / 2, s * 0.22, 1.8, fillColor=white, strokeColor=white))
    elif overall == "outside":  # square with an exclamation mark
        d.add(Rect(1, 1, s - 2, s - 2, fillColor=colour, strokeColor=colour))
        d.add(Line(s / 2, s * 0.38, s / 2, s * 0.76, strokeColor=white, strokeWidth=3))
        d.add(Circle(s / 2, s * 0.24, 1.9, fillColor=white, strokeColor=white))
    else:  # no summary: an open circle with a dash
        d.add(Circle(s / 2, s / 2, s / 2 - 1.5, fillColor=None, strokeColor=colour, strokeWidth=2))
        d.add(Line(s * 0.3, s / 2, s * 0.7, s / 2, strokeColor=colour, strokeWidth=3))
    return d


def change_mark(direction: str, size: float = 8) -> Drawing:
    """▲ up, ▼ down, ━ no change (drawn: the fonts have no arrows)."""
    d = Drawing(size, size, initialFontName="NotoSans")
    if direction == "up":
        d.add(Polygon([0.5, 1, size - 0.5, 1, size / 2, size - 0.5], fillColor=INK, strokeColor=INK))
    elif direction == "down":
        d.add(Polygon([0.5, size - 1, size - 0.5, size - 1, size / 2, 0.5], fillColor=INK, strokeColor=INK))
    else:
        d.add(Rect(0.5, size / 2 - 1, size - 1, 2, fillColor=INK, strokeColor=INK))
    return d


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    span = max(hi - lo, 1e-6)
    raw = span / n
    step = next(s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000) if s >= raw)
    first = step * int(lo // step)
    return [first + i * step for i in range(int((hi - first) // step) + 2) if lo <= first + i * step <= hi]


def chart(
    series: list[tuple[list[float], list[float | None]]],
    width: float,
    height: float,
    band: tuple[list[float], list[float], list[float]] | None = None,
    vlines: list[float] = (),  # type: ignore[assignment]
    hline: float | None = None,
    x_range: tuple[float, float] | None = None,
    x_labels: list[tuple[float, str]] | None = None,
    points: bool = False,
) -> Drawing:
    """A vector line chart. series: (xs, ys) drawn solid, dark; band: (xs, lo, hi) shaded with its mean
    dashed; vlines: dashed event markers; hline: a dashed goal line. Digits only (Noto Sans)."""
    d = Drawing(width, height, initialFontName="NotoSans")
    left, bottom, right, top = 26.0, 14.0, 4.0, 4.0
    pw, ph = width - left - right, height - bottom - top
    ys = [y for _, s in series for y in s if y is not None]
    if band:
        ys += band[1] + band[2]
    if hline is not None:
        ys.append(hline)
    if not ys:
        return d
    y0, y1 = min(ys), max(ys)
    pad = max((y1 - y0) * 0.08, 1.0)
    y0, y1 = y0 - pad, y1 + pad
    xs_all = [x for s, _ in series for x in s] + (band[0] if band else [])
    x0, x1 = x_range or (min(xs_all), max(xs_all))
    if x1 == x0:
        x0, x1 = x0 - 1, x1 + 1

    def X(x: float) -> float:
        return left + (x - x0) / (x1 - x0) * pw

    def Y(y: float) -> float:
        return bottom + (y - y0) / (y1 - y0) * ph

    d.add(Rect(left, bottom, pw, ph, fillColor=None, strokeColor=RULE, strokeWidth=0.5))
    for t in _ticks(y0, y1):
        d.add(Line(left, Y(t), left + pw, Y(t), strokeColor=colors.HexColor("#e2e8f0"), strokeWidth=0.4))
        d.add(
            String(
                left - 3,
                Y(t) - 2.5,
                f"{t:g}".replace("-", "\u2212"),
                fontName="NotoSans",
                fontSize=6.5,
                fillColor=MUTED,
                textAnchor="end",
            )
        )
    for x, label in x_labels or [(t, f"{t:g}".replace("-", "\u2212")) for t in _ticks(x0, x1)]:
        d.add(String(X(x), 3, label, fontName="NotoSans", fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
    if band:
        bx, lo, hi = band
        pts: list[float] = []
        for x, y in zip(bx, hi, strict=True):
            pts += [X(x), Y(y)]
        for x, y in zip(reversed(bx), reversed(lo), strict=True):
            pts += [X(x), Y(y)]
        d.add(Polygon(pts, fillColor=colors.HexColor("#dbe4ee"), strokeColor=None, strokeWidth=0))
        mid = [(a + b) / 2 for a, b in zip(lo, hi, strict=True)]
        line: list[float] = []
        for x, y in zip(bx, mid, strict=True):
            line += [X(x), Y(y)]
        d.add(PolyLine(line, strokeColor=MUTED, strokeWidth=0.7, strokeDashArray=[2, 2]))
    for v in vlines:
        d.add(Line(X(v), bottom, X(v), bottom + ph, strokeColor=INK, strokeWidth=0.6, strokeDashArray=[3, 2]))
    if hline is not None:
        d.add(
            Line(
                left, Y(hline), left + pw, Y(hline), strokeColor=INK, strokeWidth=0.7, strokeDashArray=[4, 2]
            )
        )
    for xs, ys_ in series:
        pts = []
        for x, yv in zip(xs, ys_, strict=True):
            if yv is not None:
                pts += [X(x), Y(yv)]
        if len(pts) >= 4:
            d.add(PolyLine(pts, strokeColor=colors.HexColor("#1d4ed8"), strokeWidth=1.6))
        if points:
            for i in range(0, len(pts), 2):
                d.add(Circle(pts[i], pts[i + 1], 1.8, fillColor=colors.HexColor("#1d4ed8"), strokeColor=None))
    return d


def skeleton(pose: dict[str, Any], size: float) -> Drawing:
    """The pose (pelvis-centred, leg lengths, x forward, y up) on a plain background (D5)."""
    d = Drawing(size, size * 1.25, initialFontName="NotoSans")
    d.add(
        Rect(0, 0, size, size * 1.25, fillColor=colors.HexColor("#f8fafc"), strokeColor=RULE, strokeWidth=0.5)
    )
    scale = size / 1.7
    ox, oy = size / 2, size * 1.25 * 0.6

    def P(xy: list[float]) -> tuple[float, float]:
        return ox + xy[0] * scale, oy + xy[1] * scale

    pelvis, shoulders = P(pose["pelvis"]), P(pose["shoulders"])
    d.add(Line(*pelvis, *shoulders, strokeColor=INK, strokeWidth=2.2))
    d.add(
        Circle(
            shoulders[0],
            shoulders[1] + 0.14 * scale,
            0.1 * scale,
            fillColor=None,
            strokeColor=INK,
            strokeWidth=1.6,
        )
    )
    for leg, colour, dash in (("trail", MUTED, [3, 2]), ("lead", colors.HexColor("#1d4ed8"), None)):
        pts = [pelvis] + [P(pose[leg][n]) for n in ("knee", "ankle", "heel", "toe")]
        flat = [v for xy in pts for v in xy]
        line = PolyLine(flat, strokeColor=colour, strokeWidth=2)
        if dash:
            line.strokeDashArray = dash
        d.add(line)
        for x, y in pts[1:]:
            d.add(Circle(x, y, 1.6, fillColor=colour, strokeColor=None))
    d.add(Circle(*pelvis, 2.2, fillColor=INK, strokeColor=None))
    return d


# ---- the report -----------------------------------------------------------------------------------
class NTable(Table):
    """A table whose cell font is Noto Sans: ReportLab's default (Helvetica) would otherwise be set in
    every cell, even one holding a paragraph."""

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "NotoSans", 8.6)]))


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    t = NTable(rows, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    style: list[Any] = [
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), HEAD_BG))
    t.setStyle(TableStyle(style))
    return t


class Report:
    def __init__(
        self,
        result: dict[str, Any],
        w: Writer,
        patient_name: str | None,
        created_at: datetime | None,
        person: Person,
        report_id: str,
        session_number: int | None,
        history: list[dict[str, Any]],
        goal_cadence: int | None,
    ) -> None:
        self.result, self.w, self.r = result, w, w.r
        self.gp = result["gait_profile"]
        self.v = self.gp["verdict"]
        self.lang = w.lang
        self.name = patient_name or self.r["details"]["not_given"]
        self.created_at = created_at
        self.person = person
        self.report_id = report_id
        self.session_number = session_number
        self.history = history
        self.goal = goal_cadence

    # -- helpers
    def date(self) -> str:
        if self.created_at is None:
            return "–"
        return self.created_at.strftime("%d %b %Y %H:%M" if self.lang == "en" else "%d-%m-%Y %H:%M")

    def t(self, both: dict[str, Any] | None) -> Any:
        return None if both is None else both[self.lang]

    def stat(self, m: str) -> dict[str, Any]:
        return self.gp["timing"].get(m) or self.gp["kinematics"].get(m) or {}

    def metric_name(self, m: str) -> str:
        return self.r["step_time"] if m == "step_time" else self.w.c["metric"][m]

    def error_text(self, m: str) -> str:
        acc = (self.result.get("accuracy") or {}).get(m) or {}
        if m == "cadence" and acc.get("error_95") is not None:
            return self.r["error_cadence"].format(e=acc["error_95"])
        if m == "step_time" and acc.get("error_95") is not None:
            return self.r["error_step_time"].format(e=acc["error_95"])
        err = (self.v["metrics"].get(m) or {}).get("error")
        if err:
            return f"±{err['mae_deg']:.1f}°"
        return self.r["not_validated"]

    def metric_rows(self, names: tuple[str, ...]) -> list[list[Any]]:
        w, r = self.w, self.r
        cols = r["columns"]
        rows: list[list[Any]] = [
            [
                w.p(cols[k], w.cell_bold)
                for k in ("metric", "value", "typical", "level", "error", "confidence")
            ]
        ]
        for m in names:
            s = self.stat(m)
            if not s:
                continue
            row = self.v["metrics"].get(m) or {}
            unit = s.get("unit", "")
            typical = row.get("typical")
            typical_text = (
                "–"
                if not typical
                else w.r["range"].format(lo=w.num(typical[0]), hi=w.with_unit(typical[1], unit))
            )
            level: Any
            if row.get("level"):
                level = NTable(
                    [[level_mark(row["level"]), w.p(w.c["level"][row["level"]], w.cell)]],
                    colWidths=[0.4 * cm, 1.9 * cm],
                    style=TableStyle(
                        [("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
                    ),
                )
            else:
                level = w.p(r["information"], w.cell)
            conf = row.get("data_confidence")
            rows.append(
                [
                    [w.p(self.metric_name(m), w.cell_bold), w.p(r["meaning"][m], w.small)],
                    w.p(w.with_unit(s.get("value"), unit, 3 if m == "step_time" else None), w.cell),
                    w.p(typical_text, w.cell),
                    level,
                    w.p(self.error_text(m), w.cell),
                    w.p(r["confidence"].get(conf, "–") if conf else "–", w.cell),
                ]
            )
        return rows

    def metric_table(self, names: tuple[str, ...]) -> Table:
        return _table(self.metric_rows(names), [5.0 * cm, 2.3 * cm, 2.8 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm])

    # -- pages
    def summary(self) -> list[Any]:
        w, r, v = self.w, self.r, self.v
        d = r["details"]
        sex, age = self.person or (None, None)
        details = [
            (d["name"], self.name),
            (d["age"], w.num(age, 0) if age is not None else d["not_given"]),
            (d["sex"], r["sex"].get(sex or "", d["not_given"])),
            (d["test"], d["walk"]),
            (d["recorded"], self.date()),
            (d["session"], str(self.session_number) if self.session_number else "–"),
            (d["report_id"], self.report_id),
        ]
        rows = []
        for i in range(0, len(details), 2):
            pair = details[i : i + 2]
            row: list[Any] = []
            for k, val in pair:
                row += [w.p(k, w.cell_bold), w.p(val, w.cell)]
            rows.append(row + [""] * (4 - len(row)))
        info = NTable(rows, colWidths=[2.4 * cm, 6.1 * cm, 2.4 * cm, 6.1 * cm], hAlign="LEFT")
        info.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("SPAN", (1, len(rows) - 1), (3, len(rows) - 1)),  # the report ID, unwrapped
                ]
            )
        )

        overall = v["overall"]
        headline = self.t(v["headline"]) if overall else r["no_verdict_title"]
        text = [
            w.p(headline, w.big),
            Spacer(1, 3),
            w.p(self.t(v["summary"])),
            Spacer(1, 3),
            w.p(self.t(v["notice"]), w.small),
        ]
        box = NTable([[overall_icon(overall), text]], colWidths=[1.7 * cm, WIDTH - 1.7 * cm], hAlign="LEFT")
        border: tuple[Any, ...]
        if overall == "typical":
            border = ("BOX", (0, 0), (-1, -1), 1.6, OVERALL_COLOUR[overall])
        elif overall == "keep_an_eye":
            border = ("BOX", (0, 0), (-1, -1), 1.6, OVERALL_COLOUR[overall], 1, [5, 3])
        elif overall == "outside":
            border = ("BOX", (0, 0), (-1, -1), 1.2, OVERALL_COLOUR[overall], 1, None, 1, 2, 2)
        else:
            border = ("BOX", (0, 0), (-1, -1), 0.8, OVERALL_COLOUR[None], 1, [1, 2])
        box.setStyle(
            TableStyle(
                [
                    border,
                    ("BACKGROUND", (0, 0), (-1, -1), OVERALL_TINT[overall]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story: list[Any] = [
            w.p(r["title"], w.title),
            w.p(r["sections"]["summary"], w.h2),
            info,
            Spacer(1, 10),
            KeepTogether([w.p(r["overall_title"], w.h3), box]),
            w.p(r["findings"], w.h3),
        ]
        findings = v["observations"][:5]
        if findings:
            for f in findings:
                story.append(
                    NTable(
                        [[level_mark(f["level"]), w.p(self.t(f["text"]))]],
                        colWidths=[0.5 * cm, WIDTH - 0.5 * cm],
                        hAlign="LEFT",
                        style=TableStyle(
                            [
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (0, 0), 4),
                            ]
                        ),
                    )
                )
        else:
            story.append(w.p(r["no_findings"] if overall else r["no_findings_no_verdict"]))
        story.append(w.p(r["next"], w.h3))
        for s in self.t(v["next_steps"]) or []:
            story.append(w.p(f"• {s}"))
        tips = (self.t(v["tips"]) or [])[:2]
        if tips:
            story.append(w.p(r["tips"], w.cell_bold))
            story += [w.p(f"• {s}") for s in tips]
        for note in self.t(v["notes"]) or []:
            story.append(w.p(note, w.small))
        story.append(w.p(r["gps"], w.h3))
        g = v.get("gps")
        if g and g.get("typical"):
            story.append(
                w.p(
                    r["gps_line"].format(
                        value=w.num(g["value"]),
                        lo=w.num(g["typical"][0]),
                        hi=w.num(g["typical"][1]),
                        label=self.t(g["label"]),
                    )
                )
            )
        else:
            story.append(w.p(r["gps_none"]))
        return story

    def timing(self) -> list[Any]:
        w, r = self.w, self.r
        return [
            PageBreak(),
            w.p(r["sections"]["timing"], w.h2),
            w.p(r["both_legs"], w.small),
            Spacer(1, 6),
            self.metric_table(TIMING_ROWS),
            Spacer(1, 4),
            *[w.p(n, w.small) for n in (self.t(self.v["notes"]) or [])],
        ]

    def curve(self, joint: str) -> list[Any]:
        w, r = self.w, self.r
        c = (self.gp["kinematics"].get("curves") or {}).get(joint)
        title = w.p(r["joint_names"][joint], w.cell_bold)
        if not c:
            return [title, w.p(r["curve_none"], w.small)]
        xs = [float(i) for i in range(len(c["mean"]))]
        band = None
        try:
            ref = ljmu_references()["curves"][joint]
            band = (
                xs,
                [m - TYPICAL_SD * s for m, s in zip(ref["mean"], ref["sd"], strict=True)],
                [m + TYPICAL_SD * s for m, s in zip(ref["mean"], ref["sd"], strict=True)],
            )
        except (FileNotFoundError, KeyError):
            pass
        stance = (self.gp["timing"].get("stance_pct") or {}).get("value")
        vlines = [0.0] + ([float(stance)] if stance else [])
        return [
            title,
            chart([(xs, c["mean"])], 8.2 * cm, 4.6 * cm, band=band, vlines=vlines, x_range=(0, 100)),
        ]

    def joints(self) -> list[Any]:
        w, r = self.w, self.r
        legend = [
            NTable(
                [
                    [self._line(), w.p(r["curve_legend"]["walk"], w.small)],
                    [self._swatch(), w.p(r["curve_legend"]["typical"], w.small)],
                    [self._dash(), w.p(r["curve_legend"]["events"], w.small)],
                ],
                colWidths=[1.2 * cm, 6.8 * cm],
                hAlign="LEFT",
            ),
            Spacer(1, 4),
            w.p(r["curve_axis_x"], w.small),
            w.p(f"y: {r['curve_axis_y']}", w.small),
        ]
        grid = NTable(
            [[self.curve("knee"), self.curve("hip")], [self.curve("ankle"), legend]],
            colWidths=[WIDTH / 2, WIDTH / 2],
            hAlign="LEFT",
        )
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        notes = [
            self.t(row["error"]["note_text"])
            for m, row in self.v["metrics"].items()
            if m in ROM_ROWS + EVENT_ROWS and row.get("error") and row["error"].get("note_text")
        ]
        return [
            PageBreak(),
            w.p(r["sections"]["joints"], w.h2),
            w.p(r["both_legs"], w.small),
            Spacer(1, 6),
            grid,
            KeepTogether([w.p(r["key_events"], w.h3), self.metric_table(EVENT_ROWS)]),
            KeepTogether([w.p(r["rom"], w.h3), self.metric_table(ROM_ROWS)]),
            *[w.p(n, w.small) for n in dict.fromkeys(notes)],
            KeepTogether(
                [w.p(r["posture"], w.h3), self.metric_table(POSTURE_ROWS), w.p(r["arm_note"], w.small)]
            ),
        ]

    def _line(self) -> Drawing:
        d = Drawing(1.0 * cm, 0.5 * cm, initialFontName="NotoSans")
        d.add(
            Line(0, 0.25 * cm, 1.0 * cm, 0.25 * cm, strokeColor=colors.HexColor("#1d4ed8"), strokeWidth=1.6)
        )
        return d

    def _swatch(self) -> Drawing:
        d = Drawing(1.0 * cm, 0.5 * cm, initialFontName="NotoSans")
        d.add(Rect(0, 3, 1.0 * cm, 0.5 * cm - 6, fillColor=colors.HexColor("#dbe4ee"), strokeColor=None))
        d.add(
            Line(
                0, 0.25 * cm, 1.0 * cm, 0.25 * cm, strokeColor=MUTED, strokeWidth=0.7, strokeDashArray=[2, 2]
            )
        )
        return d

    def _dash(self) -> Drawing:
        d = Drawing(1.0 * cm, 0.5 * cm, initialFontName="NotoSans")
        d.add(Line(0.5 * cm, 0, 0.5 * cm, 0.5 * cm, strokeColor=INK, strokeWidth=0.6, strokeDashArray=[3, 2]))
        return d

    def this_point(self) -> dict[str, Any]:
        g = self.v.get("gps") or {}
        return {
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "overall": self.v["overall"],
            "cadence": (self.gp["timing"].get("cadence") or {}).get("value"),
            "step_time_cv": (self.gp["timing"].get("step_time_cv") or {}).get("value"),
            "knee_rom": (self.gp["kinematics"].get("knee_rom") or {}).get("value"),
            "hip_rom": (self.gp["kinematics"].get("hip_rom") or {}).get("value"),
            "gps": g.get("value"),
            "this": True,
        }

    def progress(self) -> list[Any]:
        if not self.history:
            return []
        w, r = self.w, self.r
        cols = r["progress_columns"]
        series = [*self.history, self.this_point()]
        head = [w.p(cols[k], w.cell_bold) for k in ("date", "overall", *PROGRESS)]
        rows: list[list[Any]] = [head]
        for pt in series:
            day = (pt.get("created_at") or "")[:10]
            label = f"{day} ({r['this_test']})" if pt.get("this") else day
            rows.append(
                [w.p(label, w.cell), w.p(r["overall_short"].get(pt.get("overall")), w.cell)]
                + [w.p(w.num(pt.get(k)), w.cell) for k in PROGRESS]
            )
        last, now = self.history[-1], series[-1]
        change: list[Any] = [w.p(r["change"], w.cell_bold), ""]
        for k in PROGRESS:
            a, b = last.get(k), now.get(k)
            if a is None or b is None:
                change.append(w.p("–", w.cell))
                continue
            direction = "same" if abs(b - a) < SAME[k] else ("up" if b > a else "down")
            change.append(
                NTable(
                    [[change_mark(direction), w.p(r["change_words"][direction], w.cell)]],
                    colWidths=[0.4 * cm, 1.6 * cm],
                    style=TableStyle(
                        [("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
                    ),
                )
            )
        rows.append(change)
        widths = [2.9 * cm, 2.2 * cm] + [(WIDTH - 5.1 * cm) / len(PROGRESS)] * len(PROGRESS)
        table = _table(rows, widths)
        table.setStyle(TableStyle([("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), HEAD_BG)]))
        charts: list[Any] = []
        idx = list(range(len(series)))
        labels = [(float(i), (pt.get("created_at") or "")[5:10]) for i, pt in enumerate(series)]
        for k in PROGRESS:
            ys = [pt.get(k) for pt in series]
            if sum(y is not None for y in ys) < 2:
                continue
            hline = float(self.goal) if k == "cadence" and self.goal else None
            charts.append(
                [
                    w.p(cols[k], w.cell_bold),
                    chart(
                        [([float(i) for i in idx], ys)],
                        8.2 * cm,
                        3.6 * cm,
                        hline=hline,
                        x_labels=labels,
                        points=True,
                    ),
                ]
            )
        if len(charts) % 2:
            charts.append("")
        grid = NTable(
            [charts[i : i + 2] for i in range(0, len(charts), 2)],
            colWidths=[WIDTH / 2, WIDTH / 2],
            hAlign="LEFT",
        )
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story: list[Any] = [
            PageBreak(),
            w.p(r["sections"]["progress"], w.h2),
            w.p(r["progress_intro"], w.small),
            Spacer(1, 6),
            table,
            Spacer(1, 8),
            grid,
        ]
        if self.goal:
            story += [
                Spacer(1, 4),
                w.p(r["goal"].format(goal=self.goal, value=w.num(now.get("cadence")))),
                w.p(r["goal_note"], w.small),
            ]
        return story

    def method(self) -> list[Any]:
        w, r = self.w, self.r
        q, gq = self.result.get("quality") or {}, self.gp.get("quality") or {}
        qr = r["quality_rows"]
        poses = self.gp.get("poses") or {}
        snaps = [
            [skeleton(poses[k], 4.2 * cm), w.p(r["snapshot_names"][k], w.cell_bold)]
            for k in ("heel_strike", "toe_off")
            if poses.get(k)
        ]
        story: list[Any] = [PageBreak(), w.p(r["sections"]["method"], w.h2)]
        if snaps:
            t = NTable([snaps], colWidths=[5 * cm] * len(snaps), hAlign="LEFT")
            t.setStyle(
                TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
            )
            story += [w.p(r["snapshots"], w.h3), t, w.p(r["snapshot_caption"], w.small)]
        usable = q.get("usable_frame_fraction")
        rows = [
            (qr["steady"], qr["steady_value"].format(s=q.get("steady_walking_s"), passes=q.get("passes"))),
            (
                qr["frames"],
                qr["frames_value"].format(pct=round(usable * 100), total=q.get("frames_total"))
                if usable is not None
                else "–",
            ),
            (qr["steps"], qr["steps_value"].format(steps=gq.get("steps"), strides=gq.get("strides"))),
            (qr["fps"], qr["fps_value"].format(fps=q.get("fps"))),
            (qr["calibration"], qr["yes"] if q.get("calibrated") else qr["no"]),
            (qr["visibility"], w.num(gq.get("leg_visibility"), 2)),
        ]
        story += [
            w.p(r["quality"], w.h3),
            _table(
                [[w.p(a, w.cell), w.p(b, w.cell)] for a, b in rows], [6 * cm, WIDTH - 6 * cm], header=False
            ),
            Spacer(1, 3),
            w.p(r["confidence_note"], w.small),
        ]
        model = self.result.get("model") or {}
        story.append(w.p(r["method"], w.h3))
        for line in r["method_rows"]:
            story.append(
                w.p(
                    "• "
                    + line.format(
                        model=model.get("name"),
                        version=model.get("version"),
                        mediapipe=model.get("mediapipe"),
                        sha=str(model.get("sha256", ""))[:12],
                        pipeline=self.result.get("pipeline_version"),
                    ),
                    w.cell,
                )
            )
        story.append(w.p(r["errors"], w.h3))
        story += [w.p(f"• {line}", w.cell) for line in r["error_rows"]]
        story.append(w.p(r["references"], w.h3))
        story += [w.p(f"{i}. {ref}", w.small) for i, ref in enumerate(r["reference_list"], 1)]
        story += [
            w.p(r["about"], w.h3),
            w.p(self.t(self.v["disclaimer"]), w.cell),
            w.p(self.t(self.v["notice"]), w.cell),
        ]
        return story

    def story(self) -> list[Any]:
        return self.summary() + self.timing() + self.joints() + self.progress() + self.method()

    def build(self) -> bytes:
        w = self.w
        short = self.report_id.split("-")[0]
        header = w.r["header"].format(name=self.name, date=self.date(), id=short)

        def make(total: int | None) -> tuple[bytes, int]:
            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.2 * cm,
                bottomMargin=2.0 * cm, title=w.r["title"], author="GaitScan", creator="GaitScan",
                subject="", invariant=1, initialFontName="NotoSans",
            )  # fmt: skip

            def decorate(canvas: Canvas, doc: Any) -> None:
                canvas.saveState()
                top = A4[1] - 1.2 * cm
                gs = Paragraph(
                    "GaitScan", ParagraphStyle("gs", fontName="NotoSans-Bold", fontSize=9.5, leading=12)
                )
                gs.wrap(4 * cm, 1 * cm)
                gs.drawOn(canvas, 2 * cm, top - 4)
                hp = w.p(header, ParagraphStyle("hdr", parent=w.header, alignment=2))
                hp.wrap(WIDTH - 3 * cm, 1 * cm)
                hp.drawOn(canvas, 5 * cm, top - 4)
                canvas.setStrokeColor(RULE)
                canvas.setLineWidth(0.5)
                canvas.line(2 * cm, top - 8, A4[0] - 2 * cm, top - 8)
                canvas.line(2 * cm, 1.55 * cm, A4[0] - 2 * cm, 1.55 * cm)
                notice = w.p(self.t(self.v["notice"]), w.header)
                notice.wrap(WIDTH - 3.5 * cm, 1 * cm)
                notice.drawOn(canvas, 2 * cm, 1.05 * cm)
                page = w.r["page"].format(n=doc.page, total=total or "–")
                pp = w.p(page, ParagraphStyle("pg", parent=w.header, alignment=2))
                pp.wrap(3.5 * cm, 1 * cm)
                pp.drawOn(canvas, A4[0] - 5.5 * cm, 1.05 * cm)
                canvas.restoreState()

            doc.build(self.story(), onFirstPage=decorate, onLaterPages=decorate)
            return buf.getvalue(), doc.page

        _, pages = make(None)
        pdf, again = make(pages)
        assert again == pages
        return pdf


def build_report(
    result: dict[str, Any],
    patient_name: str | None,
    created_at: datetime | None,
    lang: str = "en",
    person: Person = None,
    report_id: str = "",
    session_number: int | None = None,
    history: list[dict[str, Any]] | None = None,
    goal_cadence: int | None = None,
) -> bytes:
    """The full report for a stored result that has a gait profile (schema 3)."""
    shown = present(result, person)
    if not shown or not shown.get("gait_profile"):
        raise ValueError("build_report needs a result with a gait profile; use build_pdf")
    w = Writer(lang if lang in REPORT else "en")
    return Report(
        shown, w, patient_name, created_at, person, report_id, session_number, history or [], goal_cadence
    ).build()
