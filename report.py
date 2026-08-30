"""
report.py -- Generate PDF and CSV reports from the violations database.

Usage:
  from report import generate_reports
  csv_path, pdf_path = generate_reports()
"""

import os
import datetime
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from database import get_all_violations

REPORT_DIR = "output"


def generate_reports():
    """
    Pull all violations from SQLite, produce:
      - output/violations_report.csv
      - output/violations_report.pdf

    Returns (csv_path, pdf_path).
    """
    os.makedirs(REPORT_DIR, exist_ok=True)

    rows = get_all_violations()

    # Convert to list of plain dicts for pandas
    data = [dict(r) for r in rows]

    if not data:
        print("[report] No violations in DB -- nothing to report.")
        return None, None

    df = pd.DataFrame(data)

    # ?? CSV ??????????????????????????????????????????????????????????????
    csv_path = os.path.join(REPORT_DIR, "violations_report.csv")
    df.to_csv(csv_path, index=False)
    print(f"[report] CSV saved -> {csv_path}")

    # ?? PDF ??????????????????????????????????????????????????????????????
    pdf_path = os.path.join(REPORT_DIR, "violations_report.pdf")
    _build_pdf(df, pdf_path)
    print(f"[report] PDF saved -> {pdf_path}")

    return csv_path, pdf_path


def _build_pdf(df, pdf_path):
    """Build the PDF report using ReportLab Platypus."""
    doc    = SimpleDocTemplate(pdf_path, pagesize=A4,
                               leftMargin=1.5*cm, rightMargin=1.5*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # ?? Title ?????????????????????????????????????????????????????????
    story.append(Paragraph("Traffic Violation Detection Report", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))

    # ?? Summary table (counts by type) ????????????????????????????????
    summary = df.groupby("violation_type").size().reset_index(name="count")
    story.append(Paragraph("Summary", styles["Heading2"]))
    summary_data = [["Violation Type", "Count"]]
    for _, row in summary.iterrows():
        summary_data.append([row["violation_type"], str(row["count"])])
    summary_table = Table(summary_data, colWidths=[8*cm, 4*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.darkblue),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5*cm))

    # ?? Detail table (one row per violation) ??????????????????????????
    story.append(Paragraph("Violation Details", styles["Heading2"]))

    # Columns to display in the PDF detail table
    display_cols = ["id", "timestamp", "source_video", "frame_number", "violation_type",
                    "vehicle_type", "confidence_score", "plate_text", "review_needed", "review_reason"]

    # Wrap headers and data in Paragraphs so they text-wrap instead of overflowing cells
    hdr_style = ParagraphStyle(
        'HeaderStyle', 
        parent=styles['Normal'], 
        textColor=colors.white, 
        fontName='Helvetica-Bold', 
        fontSize=7, 
        alignment=1 # Center align
    )
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
    )

    header_cells = [Paragraph(c.replace("_", " ").title(), hdr_style) for c in display_cols]
    
    # Adjusted column widths to better balance long fields and headers (sum=18.0cm)
    col_w   = [0.8*cm, 2.0*cm, 2.2*cm, 1.3*cm, 2.0*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 3.7*cm]

    detail_data = [header_cells]
    for _, row in df.iterrows():
        row_cells = []
        for c in display_cols:
            val = row.get(c, "")
            
            # Format Yes/No for review_needed
            if c == "review_needed":
                if pd.notna(val) and str(val).strip().lower() in ("1", "true", "yes", "1.0"):
                    val_str = "Yes"
                else:
                    val_str = "No"
            # Format confidence safely
            elif c == "confidence_score":
                try:
                    val_str = f"{float(val):.2f}"
                except (ValueError, TypeError):
                    val_str = str(val) if pd.notna(val) else "N/A"
            else:
                val_str = str(val) if pd.notna(val) else ""
                
            row_cells.append(Paragraph(val_str, cell_style))
            
        detail_data.append(row_cells)

    detail_table = Table(detail_data, colWidths=col_w, repeatRows=1)
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.darkblue),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.grey),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 0.5*cm))

    # ?? Thumbnails (embed evidence images where they exist) ????????????
    story.append(Paragraph("Evidence Thumbnails", styles["Heading2"]))
    thumb_added = False
    for _, row in df.iterrows():
        img_path = row.get("evidence_image_path", "")
        if img_path and os.path.exists(str(img_path)):
            caption = (f"ID {row['id']} | {row['violation_type']} | "
                       f"Frame {row['frame_number']} | Plate: {row.get('plate_text','N/A')}")
            story.append(Paragraph(caption, styles["Normal"]))
            try:
                img = Image(img_path, width=5*cm, height=3*cm)
                story.append(img)
            except Exception:
                story.append(Paragraph(f"[image not renderable: {img_path}]", styles["Normal"]))
            story.append(Spacer(1, 0.2*cm))
            thumb_added = True

    if not thumb_added:
        story.append(Paragraph("No evidence images available.", styles["Normal"]))

    doc.build(story)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    csv_p, pdf_p = generate_reports()
    if csv_p:
        print(f"[test] CSV: {csv_p}")
        print(f"[test] PDF: {pdf_p}")
    else:
        print("[test] DB is empty -- add some violations first (run database.py test).")
