from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# MODE CONFIG
# ─────────────────────────────────────────────────────────────
MODE_META = {
    "Clinical": {
        "color":          "#378ADD",
        "label":          "Clinical Mode",
        "description":    "Standard physiotherapy assessment thresholds.",
        "focus":          "General gait health, joint mobility, and symmetry.",
        "knee_si_good":   10,
        "hip_si_good":    10,
        "knee_flex_good": 50,
        "cadence_low":    80,
        "cadence_high":   140,
    },
    "Runner": {
        "color":          "#1D9E75",
        "label":          "Runner Mode",
        "description":    "Tighter symmetry targets and higher cadence standards for runners.",
        "focus":          "Running efficiency, injury prevention, and stride optimisation.",
        "knee_si_good":   8,
        "hip_si_good":    8,
        "knee_flex_good": 80,
        "cadence_low":    170,
        "cadence_high":   200,
    },
    "Athlete": {
        "color":          "#7C3AED",
        "label":          "Athlete Mode",
        "description":    "Strictest thresholds for peak biomechanical performance.",
        "focus":          "Peak efficiency, power transfer, and asymmetry elimination.",
        "knee_si_good":   5,
        "hip_si_good":    5,
        "knee_flex_good": 85,
        "cadence_low":    175,
        "cadence_high":   210,
    },
    "Elderly": {
        "color":          "#BA7517",
        "label":          "Elderly Mode",
        "description":    "Adjusted thresholds prioritising fall risk and safe movement.",
        "focus":          "Fall prevention, stability, and joint safety.",
        "knee_si_good":   15,
        "hip_si_good":    15,
        "knee_flex_good": 35,
        "cadence_low":    60,
        "cadence_high":   100,
    },
}

MODE_THRESHOLDS_TABLE = {
    "Clinical": [
        ("Knee Symmetry Index", "< 10% — normal",      "> 20% — flagged"),
        ("Hip Symmetry Index",  "< 10% — normal",      "> 20% — flagged"),
        ("Knee Flexion (Walk)", "> 50° — normal",       "< 45° — limited"),
        ("Knee Drive (Run)",    "> 70° — normal",       "< 70° — insufficient"),
        ("Cadence (Walking)",   "80–120 steps/min",     "< 80 steps/min — low"),
    ],
    "Runner": [
        ("Knee Symmetry Index", "< 8% — normal",       "> 15% — flagged"),
        ("Hip Symmetry Index",  "< 8% — normal",       "> 15% — flagged"),
        ("Knee Flexion (Walk)", "> 50° — normal",       "< 50° — limited"),
        ("Knee Drive (Run)",    "> 80° — normal",       "< 80° — insufficient"),
        ("Cadence (Running)",   "170–200 steps/min",    "< 170 steps/min — low"),
    ],
    "Athlete": [
        ("Knee Symmetry Index", "< 5% — normal",       "> 10% — flagged"),
        ("Hip Symmetry Index",  "< 5% — normal",       "> 10% — flagged"),
        ("Knee Flexion (Walk)", "> 55° — normal",       "< 55° — limited"),
        ("Knee Drive (Run)",    "> 85° — normal",       "< 85° — insufficient"),
        ("Cadence (Running)",   "175–210 steps/min",    "< 175 steps/min — low"),
    ],
    "Elderly": [
        ("Knee Symmetry Index", "< 15% — normal",      "> 25% — flagged"),
        ("Hip Symmetry Index",  "< 15% — normal",      "> 25% — flagged"),
        ("Knee Flexion (Walk)", "> 35° — normal",       "< 35° — limited"),
        ("Knee Drive (Run)",    "> 60° — normal",       "< 60° — insufficient"),
        ("Cadence (Walking)",   "60–100 steps/min",     "< 60 steps/min — low"),
    ],
}


def generate_pdf_report(scores_dict, output_path="outputs/gaitscan_report.pdf", plots_dir="outputs"):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    # ── Colours ───────────────────────────────────────────────
    mode     = scores_dict.get("mode", "Clinical")
    meta     = MODE_META.get(mode, MODE_META["Clinical"])
    MODE_HEX = meta["color"]
    MODE_CLR = colors.HexColor(MODE_HEX)

    DARK      = colors.HexColor("#1a1a2e")
    GREY      = colors.HexColor("#64748b")
    LIGHT_BG  = colors.HexColor("#f8f9fa")
    GREEN     = colors.HexColor("#1D9E75")
    RED       = colors.HexColor("#E24B4A")
    AMBER     = colors.HexColor("#BA7517")
    WHITE     = colors.white

    risk = scores_dict["scores"]["overall_risk_score"]
    if risk <= 25:
        risk_color = GREEN
        risk_label = "Low Risk"
    elif risk <= 50:
        risk_color = AMBER
        risk_label = "Moderate Concern"
    elif risk <= 75:
        risk_color = RED
        risk_label = "Significant Issues"
    else:
        risk_color = RED
        risk_label = "Serious Abnormality"

    # ── Style helper ──────────────────────────────────────────
    def S(name, **kw):
        p = ParagraphStyle(name, fontName="Helvetica", fontSize=10,
                           textColor=DARK, leading=14)
        for k, v in kw.items():
            setattr(p, k, v)
        return p

    elements = []

    # ══════════════════════════════════════════════════════════
    # HEADER BANNER
    # ══════════════════════════════════════════════════════════
    banner = Table([[
        Paragraph('<font color="white"><b>GaitScan</b></font>',
                  S("bL", fontSize=20, fontName="Helvetica-Bold",
                    textColor=WHITE, alignment=TA_LEFT, leading=24)),
        Paragraph(f'<font color="white"><b>{meta["label"]}</b></font>',
                  S("bR", fontSize=11, fontName="Helvetica-Bold",
                    textColor=WHITE, alignment=TA_RIGHT, leading=16)),
    ]], colWidths=[9*cm, 8*cm])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), MODE_CLR),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
    ]))
    elements.append(banner)
    elements.append(Spacer(1, 0.25*cm))
    elements.append(Paragraph("AI-Powered Gait &amp; Posture Analysis Report",
                               S("sub1", fontSize=9, textColor=GREY, alignment=TA_CENTER)))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
        S("sub2", fontSize=9, textColor=GREY, alignment=TA_CENTER)))
    elements.append(Spacer(1, 0.5*cm))

    activity_info = scores_dict.get("activity", {})
    if isinstance(activity_info, dict):
        activity_name = activity_info.get("activity", "—")
        confidence    = activity_info.get("confidence", "—")
    else:
        activity_name = str(activity_info)
        confidence    = "—"

    risk_hex = "#1D9E75" if risk <= 25 else "#BA7517" if risk <= 50 else "#E24B4A"

    summary = Table([[
        Paragraph(
            f'<b>Risk Score</b><br/>'
            f'<font size="26" color="{risk_hex}"><b>{risk}/100</b></font><br/>'
            f'<font size="10" color="{risk_hex}"><b>{risk_label}</b></font>',
            S("rs", alignment=TA_CENTER, leading=22)),
        Paragraph(
            f'<b>Activity Detected</b><br/>'
            f'<font size="16"><b>{activity_name}</b></font><br/>'
            f'<font size="9" color="#64748b">Confidence: {confidence}%</font>',
            S("act", alignment=TA_CENTER, leading=22)),
        Paragraph(
            f'<b>Analysis Mode</b><br/>'
            f'<font size="14"><b>{mode}</b></font><br/>'
            f'<font size="9" color="#64748b">{meta["description"]}</font>',
            S("md", alignment=TA_CENTER, leading=16)),
    ]], colWidths=[5.5*cm, 5.5*cm, 6*cm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT_BG),
        ("BOX",           (0,0), (-1,-1), 1,   colors.HexColor("#e2e8f0")),
        ("LINEAFTER",     (0,0), (1,-1),  0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ]))
    elements.append(summary)
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor("#e2e8f0"), spaceAfter=8))

    H2 = S("h2", fontSize=13, fontName="Helvetica-Bold", textColor=DARK,
            spaceBefore=12, spaceAfter=6, leading=18)

    elements.append(Paragraph("Assessment Mode Applied", H2))
    mode_box = Table([[
        Paragraph(
            f'<b>{meta["label"]}</b> — {meta["description"]}<br/>'
            f'<font size="9" color="#64748b"><b>Clinical focus:</b> {meta["focus"]}</font>',
            S("mb", leading=16, fontSize=10))
    ]], colWidths=[17*cm])
    mode_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#f0f7ff")),
        ("LINEBEFORE",    (0,0), (0,-1),  4, MODE_CLR),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ]))
    elements.append(mode_box)
    elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph("Clinical Measurements", H2))

    sc = scores_dict["scores"]
    m  = meta

    def si_status(v, good):
        if v < good:       return ("Normal",  "#1D9E75")
        if v < good * 2:   return ("Mild",    "#BA7517")
        return               ("Flagged", "#E24B4A")

    def flex_status(v):
        g = m["knee_flex_good"]
        if v >= g:           return ("Normal",     "#1D9E75")
        if v >= g * 0.7:     return ("Limited",    "#BA7517")
        return                 ("Restricted", "#E24B4A")

    def cad_status(v):
        if m["cadence_low"] <= v <= m["cadence_high"]: return ("Normal",        "#1D9E75")
        if v > 0:                                       return ("Outside Target","#BA7517")
        return                                                  ("Not Detected", "#64748b")

    rows_raw = [
        ("Knee Symmetry Index",      f"{sc['knee_symmetry_index']}%",
         si_status(sc['knee_symmetry_index'], m["knee_si_good"])),
        ("Hip Symmetry Index",       f"{sc['hip_symmetry_index']}%",
         si_status(sc['hip_symmetry_index'],  m["hip_si_good"])),
        ("Left Knee Flexion Range",  f"{sc['knee_flexion_range_L']}°",
         flex_status(sc['knee_flexion_range_L'])),
        ("Right Knee Flexion Range", f"{sc['knee_flexion_range_R']}°",
         flex_status(sc['knee_flexion_range_R'])),
        ("Estimated Cadence",        f"{sc.get('cadence', 0)} steps/min",
         cad_status(sc.get('cadence', 0))),
    ]

    meas_data = [[
        Paragraph("<b>Measurement</b>", S("mh", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10)),
        Paragraph("<b>Value</b>",       S("mh2", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10, alignment=TA_CENTER)),
        Paragraph(f"<b>Status ({mode} Mode)</b>",
                  S("mh3", textColor=WHITE, fontName="Helvetica-Bold", fontSize=10, alignment=TA_CENTER)),
    ]]
    status_clr_map = {}
    for i, (label, val, (stxt, shex)) in enumerate(rows_raw, start=1):
        meas_data.append([label, val, stxt])
        status_clr_map[i] = colors.HexColor(shex)

    meas_t = Table(meas_data, colWidths=[8*cm, 4*cm, 5*cm])
    mts = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), MODE_CLR),
        ("FONTSIZE",      (0,0), (-1,-1), 10),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [LIGHT_BG, WHITE]),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
    ])
    for row_i, clr in status_clr_map.items():
        mts.add("TEXTCOLOR", (2, row_i), (2, row_i), clr)
        mts.add("FONTNAME",  (2, row_i), (2, row_i), "Helvetica-Bold")
    meas_t.setStyle(mts)
    elements.append(meas_t)
    elements.append(Spacer(1, 0.5*cm))

    
    elements.append(Paragraph(f"Thresholds Applied — {mode} Mode", H2))
    th_data = [["Metric", "Normal Range", "Flagged When"]]
    th_data += MODE_THRESHOLDS_TABLE.get(mode, MODE_THRESHOLDS_TABLE["Clinical"])
    th_t = Table(th_data, colWidths=[6*cm, 5.5*cm, 5.5*cm])
    th_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), LIGHT_BG),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LIGHT_BG]),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("TEXTCOLOR",     (1,1), (1,-1), GREEN),
        ("TEXTCOLOR",     (2,1), (2,-1), RED),
    ]))
    elements.append(th_t)
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=1,
                               color=colors.HexColor("#e2e8f0"), spaceAfter=8))

    
    elements.append(Paragraph("Detailed Findings", H2))

    STATUS_META = {
        "good":    ("#f0fdf4", "#1D9E75", "NORMAL"),
        "mild":    ("#fffbeb", "#BA7517", "MILD"),
        "flagged": ("#fff1f2", "#E24B4A", "FLAGGED"),
    }

    for f in scores_dict["findings"]:
        if not isinstance(f, dict):
            elements.append(Paragraph(str(f), S("fb", leading=15)))
            continue
        status = f.get("status", "good")
        bg_hex, s_hex, s_lbl = STATUS_META.get(status, ("#f8f9fa", "#64748b", "INFO"))
        metric = f.get("metric", "")
        value  = f.get("value", "")
        plain  = f.get("plain_english", "")

        fd = Table([[
            Paragraph(
                f'<font color="{s_hex}"><b>{s_lbl}</b></font>   '
                f'<b>{metric}</b>   '
                f'<font size="9" color="#64748b">{value}</font><br/>'
                f'<font size="9" color="#374151">{plain}</font>',
                S("fd", leading=15, fontSize=10))
        ]], colWidths=[17*cm])
        fd.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor(bg_hex)),
            ("LINEBEFORE",    (0,0), (0,-1),  4, colors.HexColor(s_hex)),
            ("TOPPADDING",    (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LEFTPADDING",   (0,0), (-1,-1), 14),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ]))
        elements.append(fd)
        elements.append(Spacer(1, 0.2*cm))

    elements.append(Spacer(1, 0.3*cm))

    
    if scores_dict.get("recommendations"):
        elements.append(Paragraph("Recommendations", H2))
        for r in scores_dict["recommendations"]:
            rd = Table([[
                Paragraph(f"→  {r}", S("rec", fontSize=10, leading=15))
            ]], colWidths=[17*cm])
            rd.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#fffbeb")),
                ("LINEBEFORE",    (0,0), (0,-1),  4, AMBER),
                ("TOPPADDING",    (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
                ("LEFTPADDING",   (0,0), (-1,-1), 14),
            ]))
            elements.append(rd)
            elements.append(Spacer(1, 0.15*cm))
        elements.append(Spacer(1, 0.3*cm))

    
    exercises = scores_dict.get("exercises", [])
    if exercises:
        elements.append(HRFlowable(width="100%", thickness=1,
                                   color=colors.HexColor("#e2e8f0"), spaceAfter=8))
        elements.append(Paragraph("Prescribed Exercises", H2))
        elements.append(Paragraph(
            f"Personalised to your findings under {mode} Mode.",
            S("exsub", fontSize=9, textColor=GREY, spaceAfter=8, leading=13)))

        DIFF_COLORS = {
            "Easy":     ("#dcfce7", "#166534"),
            "Moderate": ("#fef9c3", "#713f12"),
            "Hard":     ("#fee2e2", "#7f1d1d"),
        }
        for i, ex in enumerate(exercises):
            diff = ex.get("difficulty", "Easy")
            diff_bg, diff_fg = DIFF_COLORS.get(diff, ("#f1f5f9", "#1a1a2e"))
            ex_t = Table([[
                Paragraph(
                    f'<b>{i+1}. {ex["name"]}</b>  '
                    f'<font size="8" color="#64748b">{ex.get("muscle","")}</font><br/>'
                    f'<font size="9" color="{MODE_HEX}"><b>Why for you:</b> {ex.get("why","")}</font><br/>'
                    f'<font size="9" color="#374151"><b>How:</b> {ex.get("instructions","")}</font>',
                    S("ex", leading=15, fontSize=10)),
                Paragraph(
                    f'<font color="{diff_fg}"><b>{diff}</b></font>',
                    S("dff", fontSize=8, alignment=TA_CENTER,
                      textColor=colors.HexColor(diff_fg))),
            ]], colWidths=[14.5*cm, 2.5*cm])
            ex_t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), LIGHT_BG),
                ("BACKGROUND",    (1,0), (1,-1),  colors.HexColor(diff_bg)),
                ("LINEBEFORE",    (0,0), (0,-1),  4, MODE_CLR),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",    (0,0), (-1,-1), 10),
                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ("LEFTPADDING",   (0,0), (-1,-1), 14),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                ("ALIGN",         (1,0), (1,-1),  "CENTER"),
            ]))
            elements.append(ex_t)
            elements.append(Spacer(1, 0.2*cm))
        elements.append(Spacer(1, 0.3*cm))

    
    plot_files = [
        ("knee_angles.png",      "Knee Flexion Angle — Left vs Right Over Time"),
        ("hip_angles.png",       "Hip Flexion Angle — Left vs Right Over Time"),
        ("symmetry_summary.png", "Symmetry Summary"),
        ("ankle_trajectory.png", "Ankle Trajectory"),
    ]
    if any(os.path.exists(os.path.join(plots_dir, f)) for f, _ in plot_files):
        elements.append(HRFlowable(width="100%", thickness=1,
                                   color=colors.HexColor("#e2e8f0"), spaceAfter=8))
        elements.append(Paragraph("Gait Analysis Charts", H2))
        for fname, cap in plot_files:
            fpath = os.path.join(plots_dir, fname)
            if os.path.exists(fpath):
                elements.append(Image(fpath, width=15*cm, height=6*cm))
                elements.append(Paragraph(cap,
                    S("cap", fontSize=8, textColor=GREY,
                      alignment=TA_CENTER, spaceAfter=6)))
                elements.append(Spacer(1, 0.3*cm))


    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                               color=colors.HexColor("#e2e8f0"), spaceAfter=6))
    footer = S("ft", fontSize=7.5, textColor=GREY, alignment=TA_CENTER, leading=12)
    elements.append(Paragraph(
        f"GaitScan — AI-Powered Gait Analysis  |  Mode: {mode}  |  "
        f"Generated {datetime.now().strftime('%d %B %Y')}", footer))
    elements.append(Paragraph(
        "This report is for informational purposes only and does not constitute medical advice. "
        "Please consult a qualified physiotherapist or physician for clinical decisions.", footer))

    doc.build(elements)
    print(f"  Report saved: {output_path}")
    return output_path