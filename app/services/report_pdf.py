import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from gaitcore.legacy import DISCLAIMER, summary_for_score

# ─────────────────────────────────────────────────────────────
# MODE CONFIG
# ─────────────────────────────────────────────────────────────
MODE_META = {
    "Clinical": {
        "color": "#378ADD",
        "label": "Clinical Mode",
        "description": "General reference thresholds (not clinically validated).",
        "focus": "Joint motion and left-right symmetry.",
        "knee_si_good": 10,
        "hip_si_good": 10,
        "knee_flex_good": 50,
        "cadence_low": 80,
        "cadence_high": 140,
    },
    "Runner": {
        "color": "#1D9E75",
        "label": "Runner Mode",
        "description": "Tighter symmetry and higher cadence reference ranges for runners (not clinically validated).",
        "focus": "Running cadence, knee drive and symmetry.",
        "knee_si_good": 8,
        "hip_si_good": 8,
        "knee_flex_good": 80,
        "cadence_low": 170,
        "cadence_high": 200,
    },
    "Athlete": {
        "color": "#7C3AED",
        "label": "Athlete Mode",
        "description": "Strictest reference ranges (not clinically validated).",
        "focus": "Symmetry and cadence against strict reference ranges.",
        "knee_si_good": 5,
        "hip_si_good": 5,
        "knee_flex_good": 85,
        "cadence_low": 175,
        "cadence_high": 210,
    },
    "Elderly": {
        "color": "#BA7517",
        "label": "Elderly Mode",
        "description": "Wider reference ranges intended for older adults (not clinically validated).",
        "focus": "Joint motion and step rate against wider reference ranges.",
        "knee_si_good": 15,
        "hip_si_good": 15,
        "knee_flex_good": 35,
        "cadence_low": 60,
        "cadence_high": 100,
    },
}

UNKNOWN_MODE_META = {
    "color": "#64748b",
    "label": "Mode not recorded",
    "description": "This session was analysed before the analysis mode was stored.",
    "focus": "Reference thresholds are not shown because the mode is unknown.",
}

MODE_THRESHOLDS_TABLE = {
    "Clinical": [
        ("Knee Symmetry Index", "< 10%", "> 20%"),
        ("Hip Symmetry Index", "< 10%", "> 20%"),
        ("Knee Flexion (Walk)", "> 50°", "< 45° — limited"),
        ("Knee Drive (Run)", "> 70°", "< 70° — insufficient"),
        ("Cadence (Walking)", "80–120 steps/min", "< 80 steps/min — low"),
    ],
    "Runner": [
        ("Knee Symmetry Index", "< 8%", "> 15%"),
        ("Hip Symmetry Index", "< 8%", "> 15%"),
        ("Knee Flexion (Walk)", "> 50°", "< 50° — limited"),
        ("Knee Drive (Run)", "> 80°", "< 80° — insufficient"),
        ("Cadence (Running)", "170–200 steps/min", "< 170 steps/min — low"),
    ],
    "Athlete": [
        ("Knee Symmetry Index", "< 5%", "> 10%"),
        ("Hip Symmetry Index", "< 5%", "> 10%"),
        ("Knee Flexion (Walk)", "> 55°", "< 55° — limited"),
        ("Knee Drive (Run)", "> 85°", "< 85° — insufficient"),
        ("Cadence (Running)", "175–210 steps/min", "< 175 steps/min — low"),
    ],
    "Elderly": [
        ("Knee Symmetry Index", "< 15%", "> 25%"),
        ("Hip Symmetry Index", "< 15%", "> 25%"),
        ("Knee Flexion (Walk)", "> 35°", "< 35° — limited"),
        ("Knee Drive (Run)", "> 60°", "< 60° — insufficient"),
        ("Cadence (Walking)", "60–100 steps/min", "< 60 steps/min — low"),
    ],
}


def generate_pdf_report(scores_dict, output_path="outputs/gaitscan_report.pdf", plots_dir="outputs"):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
    )

    # ── Colours ───────────────────────────────────────────────
    # Sessions stored before the mode column existed have mode=None: say so rather
    # than silently applying Clinical thresholds (F15).
    mode_known = scores_dict.get("mode") in MODE_META
    mode = scores_dict["mode"] if mode_known else "Not recorded"
    meta = MODE_META[mode] if mode_known else UNKNOWN_MODE_META
    MODE_HEX = meta["color"]
    MODE_CLR = colors.HexColor(MODE_HEX)

    DARK = colors.HexColor("#1a1a2e")
    GREY = colors.HexColor("#64748b")
    LIGHT_BG = colors.HexColor("#f8f9fa")
    GREEN = colors.HexColor("#1D9E75")
    RED = colors.HexColor("#E24B4A")
    AMBER = colors.HexColor("#BA7517")
    WHITE = colors.white

    summary_label, summary_meaning, summary_colour = summary_for_score(
        scores_dict["scores"]["overall_risk_score"]
    )

    # ── Style helper ──────────────────────────────────────────
    def S(name, **kw):
        p = ParagraphStyle(name, fontName="Helvetica", fontSize=10, textColor=DARK, leading=14)
        for k, v in kw.items():
            setattr(p, k, v)
        return p

    def esc(v):
        """Escape text for ReportLab's mini-markup (a bare '<' or '&' otherwise aborts the build)."""
        return escape(str(v))

    elements = []

    # ══════════════════════════════════════════════════════════
    # HEADER BANNER
    # ══════════════════════════════════════════════════════════
    banner = Table(
        [
            [
                Paragraph(
                    '<font color="white"><b>GaitScan</b></font>',
                    S(
                        "bL",
                        fontSize=20,
                        fontName="Helvetica-Bold",
                        textColor=WHITE,
                        alignment=TA_LEFT,
                        leading=24,
                    ),
                ),
                Paragraph(
                    f'<font color="white"><b>{meta["label"]}</b></font>',
                    S(
                        "bR",
                        fontSize=11,
                        fontName="Helvetica-Bold",
                        textColor=WHITE,
                        alignment=TA_RIGHT,
                        leading=16,
                    ),
                ),
            ]
        ],
        colWidths=[9 * cm, 8 * cm],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), MODE_CLR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    elements.append(banner)
    elements.append(Spacer(1, 0.25 * cm))
    elements.append(
        Paragraph(
            "Gait Measurement Report — experimental, not clinically validated",
            S("sub1", fontSize=9, textColor=GREY, alignment=TA_CENTER),
        )
    )
    elements.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
            S("sub2", fontSize=9, textColor=GREY, alignment=TA_CENTER),
        )
    )
    elements.append(Spacer(1, 0.3 * cm))
    notice = Table(
        [[Paragraph(esc(DISCLAIMER), S("notice", fontSize=8.5, leading=12, textColor=DARK))]],
        colWidths=[17 * cm],
    )
    notice.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                ("BOX", (0, 0), (-1, -1), 0.5, AMBER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elements.append(notice)
    elements.append(Spacer(1, 0.4 * cm))

    activity_info = scores_dict.get("activity", {})
    if isinstance(activity_info, dict):
        activity_name = activity_info.get("activity", "—")
        confidence = activity_info.get("confidence", "—")
    else:
        activity_name = str(activity_info)
        confidence = "—"

    summary_hex = "#1D9E75" if summary_colour == "green" else "#BA7517"

    summary = Table(
        [
            [
                Paragraph(
                    f"<b>Summary</b><br/>"
                    f'<font size="14" color="{summary_hex}"><b>{esc(summary_label)}</b></font><br/>'
                    f'<font size="8" color="#64748b">{esc(summary_meaning)}</font>',
                    S("rs", alignment=TA_CENTER, leading=16),
                ),
                Paragraph(
                    f"<b>Activity Detected</b><br/>"
                    f'<font size="16"><b>{esc(activity_name)}</b></font><br/>'
                    f'<font size="9" color="#64748b">Confidence: {esc(confidence)}%</font>',
                    S("act", alignment=TA_CENTER, leading=22),
                ),
                Paragraph(
                    f"<b>Analysis Mode</b><br/>"
                    f'<font size="14"><b>{esc(mode)}</b></font><br/>'
                    f'<font size="9" color="#64748b">{meta["description"]}</font>',
                    S("md", alignment=TA_CENTER, leading=16),
                ),
            ]
        ],
        colWidths=[5.5 * cm, 5.5 * cm, 6 * cm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                ("LINEAFTER", (0, 0), (1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elements.append(summary)
    elements.append(Spacer(1, 0.5 * cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8))

    H2 = S(
        "h2", fontSize=13, fontName="Helvetica-Bold", textColor=DARK, spaceBefore=12, spaceAfter=6, leading=18
    )

    elements.append(Paragraph("Assessment Mode Applied", H2))
    mode_box = Table(
        [
            [
                Paragraph(
                    f"<b>{meta['label']}</b> — {meta['description']}<br/>"
                    f'<font size="9" color="#64748b"><b>Focus:</b> {meta["focus"]}</font>',
                    S("mb", leading=16, fontSize=10),
                )
            ]
        ],
        colWidths=[17 * cm],
    )
    mode_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f7ff")),
                ("LINEBEFORE", (0, 0), (0, -1), 4, MODE_CLR),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elements.append(mode_box)
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("Measurements", H2))

    sc = scores_dict["scores"]
    m = meta

    def si_status(v, good):
        if not mode_known:
            return ("—", "#64748b")
        if v < good:
            return ("Within range", "#1D9E75")
        if v < good * 2:
            return ("Near edge", "#BA7517")
        return ("Outside range", "#E24B4A")

    def flex_status(v):
        if not mode_known:
            return ("—", "#64748b")
        g = m["knee_flex_good"]
        if v >= g:
            return ("Within range", "#1D9E75")
        if v >= g * 0.7:
            return ("Near edge", "#BA7517")
        return ("Outside range", "#E24B4A")

    def cad_status(v):
        if not mode_known:
            return ("—", "#64748b")
        if m["cadence_low"] <= v <= m["cadence_high"]:
            return ("Within range", "#1D9E75")
        if v > 0:
            return ("Outside range", "#BA7517")
        return ("Not Detected", "#64748b")

    rows_raw = [
        (
            "Knee Symmetry Index",
            f"{sc['knee_symmetry_index']}%",
            si_status(sc["knee_symmetry_index"], m.get("knee_si_good")),
        ),
        (
            "Hip Symmetry Index",
            f"{sc['hip_symmetry_index']}%",
            si_status(sc["hip_symmetry_index"], m.get("hip_si_good")),
        ),
        (
            "Left Knee Flexion Range",
            f"{sc['knee_flexion_range_L']}°",
            flex_status(sc["knee_flexion_range_L"]),
        ),
        (
            "Right Knee Flexion Range",
            f"{sc['knee_flexion_range_R']}°",
            flex_status(sc["knee_flexion_range_R"]),
        ),
        ("Estimated Cadence", f"{sc.get('cadence', 0)} steps/min", cad_status(sc.get("cadence", 0))),
    ]

    meas_data = [
        [
            Paragraph("<b>Measurement</b>", S("mh", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10)),
            Paragraph(
                "<b>Value</b>",
                S("mh2", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10, alignment=TA_CENTER),
            ),
            Paragraph(
                f"<b>Status ({meta['label']})</b>",
                S("mh3", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10, alignment=TA_CENTER),
            ),
        ]
    ]
    status_clr_map = {}
    for i, (label, val, (stxt, shex)) in enumerate(rows_raw, start=1):
        meas_data.append([label, val, stxt])
        status_clr_map[i] = colors.HexColor(shex)

    meas_t = Table(meas_data, colWidths=[8 * cm, 4 * cm, 5 * cm])
    mts = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), MODE_CLR),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_BG, WHITE]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ]
    )
    for row_i, clr in status_clr_map.items():
        mts.add("TEXTCOLOR", (2, row_i), (2, row_i), clr)
        mts.add("FONTNAME", (2, row_i), (2, row_i), "Helvetica-Bold")
    meas_t.setStyle(mts)
    elements.append(meas_t)
    elements.append(Spacer(1, 0.5 * cm))

    if not mode_known:
        elements.append(
            Paragraph(
                "Reference thresholds are not shown: this session's analysis mode was not recorded.",
                S("nomode", fontSize=9, textColor=GREY),
            )
        )
    th_data = [["Metric", "Reference Range", "Outside Range When"]]
    th_data += MODE_THRESHOLDS_TABLE.get(mode, [])
    if mode_known:
        elements.append(Paragraph(f"Thresholds Applied — {mode} Mode", H2))
        th_t = Table(th_data, colWidths=[6 * cm, 5.5 * cm, 5.5 * cm])
        th_t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("TEXTCOLOR", (1, 1), (1, -1), GREEN),
                    ("TEXTCOLOR", (2, 1), (2, -1), RED),
                ]
            )
        )
        elements.append(th_t)
    elements.append(Spacer(1, 0.5 * cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8))

    elements.append(Paragraph("Measurement Details", H2))

    STATUS_META = {
        "good": ("#f0fdf4", "#1D9E75", "WITHIN RANGE"),
        "mild": ("#fffbeb", "#BA7517", "NEAR EDGE"),
        "flagged": ("#fff1f2", "#E24B4A", "OUTSIDE RANGE"),
    }

    for f in scores_dict["findings"]:
        if not isinstance(f, dict):
            elements.append(Paragraph(str(f), S("fb", leading=15)))
            continue
        status = f.get("status", "good")
        bg_hex, s_hex, s_lbl = STATUS_META.get(status, ("#f8f9fa", "#64748b", "INFO"))
        metric = f.get("metric", "")
        value = f.get("value", "")
        plain = f.get("plain_english", "")

        fd = Table(
            [
                [
                    Paragraph(
                        f'<font color="{s_hex}"><b>{s_lbl}</b></font>   '
                        f"<b>{esc(metric)}</b>   "
                        f'<font size="9" color="#64748b">{esc(value)}</font><br/>'
                        f'<font size="9" color="#374151">{esc(plain)}</font>',
                        S("fd", leading=15, fontSize=10),
                    )
                ]
            ],
            colWidths=[17 * cm],
        )
        fd.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor(s_hex)),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(fd)
        elements.append(Spacer(1, 0.2 * cm))

    elements.append(Spacer(1, 0.3 * cm))

    if scores_dict.get("recommendations"):
        elements.append(Paragraph("Discussion Points", H2))
        for r in scores_dict["recommendations"]:
            rd = Table([[Paragraph(f"→  {esc(r)}", S("rec", fontSize=10, leading=15))]], colWidths=[17 * cm])
            rd.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
                        ("LINEBEFORE", (0, 0), (0, -1), 4, AMBER),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ]
                )
            )
            elements.append(rd)
            elements.append(Spacer(1, 0.15 * cm))
        elements.append(Spacer(1, 0.3 * cm))

    exercises = scores_dict.get("exercises", [])
    if exercises:
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8))
        elements.append(Paragraph("Exercises to Discuss with Your Physiotherapist", H2))
        elements.append(
            Paragraph(
                "General exercises matched to the measurements above. Not a treatment plan.",
                S("exsub", fontSize=9, textColor=GREY, spaceAfter=8, leading=13),
            )
        )

        DIFF_COLORS = {
            "Easy": ("#dcfce7", "#166534"),
            "Moderate": ("#fef9c3", "#713f12"),
            "Hard": ("#fee2e2", "#7f1d1d"),
        }
        for i, ex in enumerate(exercises):
            diff = ex.get("difficulty", "Easy")
            diff_bg, diff_fg = DIFF_COLORS.get(diff, ("#f1f5f9", "#1a1a2e"))
            ex_t = Table(
                [
                    [
                        Paragraph(
                            f"<b>{i + 1}. {esc(ex['name'])}</b>  "
                            f'<font size="8" color="#64748b">{esc(ex.get("muscle", ""))}</font><br/>'
                            f'<font size="9" color="{MODE_HEX}"><b>Why this may help:</b> {esc(ex.get("why", ""))}</font><br/>'
                            f'<font size="9" color="#374151"><b>How:</b> {esc(ex.get("instructions", ""))}</font>',
                            S("ex", leading=15, fontSize=10),
                        ),
                        Paragraph(
                            f'<font color="{diff_fg}"><b>{esc(diff)}</b></font>',
                            S("dff", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor(diff_fg)),
                        ),
                    ]
                ],
                colWidths=[14.5 * cm, 2.5 * cm],
            )
            ex_t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor(diff_bg)),
                        ("LINEBEFORE", (0, 0), (0, -1), 4, MODE_CLR),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                        ("LEFTPADDING", (0, 0), (-1, -1), 14),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ]
                )
            )
            elements.append(ex_t)
            elements.append(Spacer(1, 0.2 * cm))
        elements.append(Spacer(1, 0.3 * cm))

    plot_files = [
        ("knee_angles.png", "Knee Flexion Angle — Left vs Right Over Time"),
        ("hip_angles.png", "Hip Flexion Angle — Left vs Right Over Time"),
        ("symmetry_summary.png", "Symmetry Summary"),
        ("ankle_trajectory.png", "Ankle Trajectory"),
    ]
    if any(os.path.exists(os.path.join(plots_dir, f)) for f, _ in plot_files):
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8))
        elements.append(Paragraph("Gait Analysis Charts", H2))
        for fname, cap in plot_files:
            fpath = os.path.join(plots_dir, fname)
            if os.path.exists(fpath):
                elements.append(Image(fpath, width=15 * cm, height=6 * cm))
                elements.append(
                    Paragraph(cap, S("cap", fontSize=8, textColor=GREY, alignment=TA_CENTER, spaceAfter=6))
                )
                elements.append(Spacer(1, 0.3 * cm))

    elements.append(Spacer(1, 0.5 * cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=6))
    footer = S("ft", fontSize=7.5, textColor=GREY, alignment=TA_CENTER, leading=12)
    elements.append(
        Paragraph(
            f"GaitScan — gait measurement (experimental)  |  Mode: {esc(mode)}  |  "
            f"Generated {datetime.now().strftime('%d %B %Y')}",
            footer,
        )
    )
    elements.append(Paragraph(esc(DISCLAIMER), footer))

    doc.build(elements)
    print(f"  Report saved: {output_path}")
    return output_path
