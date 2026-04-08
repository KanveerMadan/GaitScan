from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os
from datetime import datetime

def generate_pdf_report(scores_dict, output_path="outputs/gaitscan_report.pdf", plots_dir="outputs"):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    elements = []

    
    DARK    = colors.HexColor("#1a1a2e")
    BLUE    = colors.HexColor("#378ADD")
    GREEN   = colors.HexColor("#1D9E75")
    RED     = colors.HexColor("#E24B4A")
    AMBER   = colors.HexColor("#BA7517")
    LIGHT   = colors.HexColor("#f8f9fa")

    
    title_style = ParagraphStyle("title",
        fontSize=26, fontName="Helvetica-Bold",
        textColor=DARK, alignment=TA_CENTER, spaceAfter=4)
    sub_style = ParagraphStyle("sub",
        fontSize=11, fontName="Helvetica",
        textColor=colors.HexColor("#666666"), alignment=TA_CENTER, spaceAfter=2)

    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph("GaitScan", title_style))
    elements.append(Paragraph("AI-Powered Gait & Posture Analysis Report", sub_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", sub_style))
    elements.append(Spacer(1, 0.8*cm))

    
    risk = scores_dict["scores"]["overall_risk_score"]
    if risk == 0:
        risk_label = "LOW RISK"
        risk_color = GREEN
    elif risk <= 30:
        risk_label = "MODERATE RISK"
        risk_color = AMBER
    else:
        risk_label = "HIGH RISK"
        risk_color = RED

    risk_style = ParagraphStyle("risk",
        fontSize=20, fontName="Helvetica-Bold",
        textColor=risk_color, alignment=TA_CENTER, spaceAfter=4)
    risk_sub = ParagraphStyle("risksub",
        fontSize=11, fontName="Helvetica",
        textColor=colors.HexColor("#444444"), alignment=TA_CENTER)

    elements.append(Paragraph(f"Overall Assessment: {risk_label}", risk_style))
    elements.append(Paragraph(f"Risk Score: {risk}/100", risk_sub))
    elements.append(Spacer(1, 0.8*cm))

    
    section_style = ParagraphStyle("section",
        fontSize=14, fontName="Helvetica-Bold",
        textColor=DARK, spaceBefore=12, spaceAfter=8)
    elements.append(Paragraph("Clinical Measurements", section_style))

    s = scores_dict["scores"]
    table_data = [
        ["Measurement", "Value", "Status"],
        ["Knee Symmetry Index",    f"{s['knee_symmetry_index']}%",
         "Normal" if s['knee_symmetry_index'] < 10 else "Asymmetric"],
        ["Hip Symmetry Index",     f"{s['hip_symmetry_index']}%",
         "Normal" if s['hip_symmetry_index'] < 10 else "Asymmetric"],
        ["Left Knee Flexion Range",  f"{s['knee_flexion_range_L']}°",
         "Normal" if s['knee_flexion_range_L'] > 50 else "Limited"],
        ["Right Knee Flexion Range", f"{s['knee_flexion_range_R']}°",
         "Normal" if s['knee_flexion_range_R'] > 50 else "Limited"],
        ["Estimated Cadence",        f"{s['estimated_cadence_steps_per_min']} steps/min",
         "Normal" if 80 <= s['estimated_cadence_steps_per_min'] <= 140 else "Check"],
    ]

    def status_color(val):
        if val in ("Normal",): return GREEN
        if val in ("Limited", "Asymmetric", "Check"): return AMBER
        return DARK

    col_widths = [9*cm, 4*cm, 4*cm]
    table = Table(table_data, colWidths=col_widths)
    table_style = [
        ("BACKGROUND",  (0,0), (-1,0), BLUE),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("FONTNAME",    (0,1), (-1,-1), "Helvetica"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#dddddd")),
        ("ALIGN",       (1,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0),(-1,-1), 7),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]
    for row_idx, row in enumerate(table_data[1:], start=1):
        status = row[2]
        c = status_color(status)
        table_style.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), c))
        table_style.append(("FONTNAME",  (2, row_idx), (2, row_idx), "Helvetica-Bold"))

    table.setStyle(TableStyle(table_style))
    elements.append(table)
    elements.append(Spacer(1, 0.8*cm))

    # --- Findings ---
    elements.append(Paragraph("Findings", section_style))
    finding_style = ParagraphStyle("finding",
        fontSize=10, fontName="Helvetica",
        textColor=DARK, leftIndent=12, spaceAfter=5, leading=15)
    for f in scores_dict["findings"]:
        elements.append(Paragraph(f"• {f}", finding_style))
    elements.append(Spacer(1, 0.5*cm))

    # --- Recommendations ---
    if scores_dict["recommendations"]:
        elements.append(Paragraph("Recommendations", section_style))
        for r in scores_dict["recommendations"]:
            elements.append(Paragraph(f"→ {r}", finding_style))
        elements.append(Spacer(1, 0.5*cm))

    
    elements.append(Paragraph("Gait Analysis Charts", section_style))
    plot_files = [
        ("knee_angles.png",       "Knee Flexion — Left vs Right"),
        ("hip_angles.png",        "Hip Flexion — Left vs Right"),
        ("symmetry_summary.png",  "Symmetry Summary"),
        ("ankle_trajectory.png",  "Ankle Trajectory"),
    ]
    for fname, caption in plot_files:
        fpath = os.path.join(plots_dir, fname)
        if os.path.exists(fpath):
            img = Image(fpath, width=15*cm, height=6*cm)
            elements.append(img)
            cap_style = ParagraphStyle("cap",
                fontSize=9, fontName="Helvetica",
                textColor=colors.HexColor("#888888"),
                alignment=TA_CENTER, spaceAfter=10)
            elements.append(Paragraph(caption, cap_style))
            elements.append(Spacer(1, 0.3*cm))

    
    elements.append(Spacer(1, 0.5*cm))
    footer_style = ParagraphStyle("footer",
        fontSize=8, fontName="Helvetica",
        textColor=colors.HexColor("#aaaaaa"), alignment=TA_CENTER)
    elements.append(Paragraph(
        "GaitScan — AI Gait Analysis | This report is for informational purposes only. "
        "Consult a qualified physiotherapist for clinical decisions.", footer_style))

    doc.build(elements)
    print(f"  Report saved: {output_path}")
    return output_path