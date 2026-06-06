import os
import logging
import numpy as np
from datetime  import datetime
from typing    import List, Dict, Optional

logger = logging.getLogger(__name__)


class PDFReporter:
    """
    Generates professional PDF reports using ReportLab.

    Report sections:
    1. Cover page — system name, date range, camera ID
    2. Executive summary — KPI cards (detections, alerts, top class)
    3. Detection analysis — bar chart + hourly table
    4. Alert summary — alert types table + stats
    5. Zone analysis — dwell times, top zones
    6. Line crossing summary — in/out counts per line
    7. Heatmap image (if available)
    """

    def __init__(self, config: dict):
        cfg             = config.get("reports", {})
        self.output_dir = cfg.get("output_dir",    "data/reports")
        self.company    = cfg.get("company_name",  "Surveillance System")
        self.logo_path  = cfg.get("logo_path",     "")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(
        self,
        analytics,
        hours        : int = 24,
        heatmap_path : Optional[str] = None,
        camera_id    : str = "cam_0"
    ) -> str:
        """
        Generate a complete PDF report.

        Args:
            analytics   : Analytics instance from Layer 3
            hours       : Time range for report data
            heatmap_path: Optional path to saved heatmap image
            camera_id   : Camera identifier for report header

        Returns:
            Path to the generated PDF file.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib           import colors
            from reportlab.lib.styles    import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units     import cm
            from reportlab.platypus      import (
                SimpleDocTemplate, Paragraph, Spacer,
                Table, TableStyle, Image, HRFlowable,
                PageBreak
            )
        except ImportError:
            logger.error("reportlab not installed. Run: pip install reportlab")
            return ""

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{camera_id}_{ts}.pdf"
        path     = os.path.join(self.output_dir, filename)

        doc   = SimpleDocTemplate(
            path, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm,   bottomMargin=2*cm
        )
        story = []
        styles= getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent     = styles["Title"],
            fontSize   = 24,
            textColor  = colors.HexColor("#1a1a2e"),
            spaceAfter = 12
        )
        h1_style = ParagraphStyle(
            "H1",
            parent     = styles["Heading1"],
            fontSize   = 16,
            textColor  = colors.HexColor("#1a1a2e"),
            spaceBefore= 16,
            spaceAfter = 8,
            borderPad  = 4
        )
        h2_style = ParagraphStyle(
            "H2",
            parent    = styles["Heading2"],
            fontSize  = 13,
            textColor = colors.HexColor("#16213e"),
            spaceBefore=10,
            spaceAfter= 6
        )
        body_style = ParagraphStyle(
            "Body",
            parent    = styles["Normal"],
            fontSize  = 10,
            textColor = colors.HexColor("#333333"),
            spaceAfter= 4
        )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Cover Page ────────────────────────────────────────────────────
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(self.company, title_style))
        story.append(Paragraph(
            "Intelligent Surveillance Analytics Report", h1_style
        ))
        story.append(HRFlowable(
            width="100%", thickness=2,
            color=colors.HexColor("#4FC3F7")
        ))
        story.append(Spacer(1, 0.5*cm))

        meta = [
            ["Generated:", now_str],
            ["Camera:", camera_id],
            ["Report Period:", f"Last {hours} hours"],
            ["Report Type:", "Automated Analytics Report"]
        ]
        meta_table = Table(meta, colWidths=[4*cm, 12*cm])
        meta_table.setStyle(TableStyle([
            ("FONTSIZE",    (0,0), (-1,-1), 10),
            ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
            ("TEXTCOLOR",   (0,0), (0,-1), colors.HexColor("#444444")),
            ("TEXTCOLOR",   (1,0), (1,-1), colors.HexColor("#222222")),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),
             [colors.HexColor("#f8f9fa"), colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#e0e0e0")),
            ("PADDING",     (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(PageBreak())

        # ── Executive Summary ─────────────────────────────────────────────
        story.append(Paragraph("Executive Summary", h1_style))

        total_detections = analytics.total_detections(hours)
        total_alerts     = analytics.total_alerts(hours)
        unacknowledged   = analytics.unacknowledged_alerts()
        by_class         = analytics.detections_by_class(hours)
        top_class        = by_class[0]["class_name"] if by_class else "N/A"
        top_count        = by_class[0]["count"]      if by_class else 0

        summary_data = [
            ["Metric",               "Value",        "Period"],
            ["Total Detections",     f"{total_detections:,}", f"Last {hours}h"],
            ["Total Alerts",         f"{total_alerts:,}",     f"Last {hours}h"],
            ["Unacknowledged Alerts",f"{unacknowledged:,}",   "Current"],
            ["Top Detected Class",   top_class.title(),       f"{top_count:,} detections"],
        ]
        summary_table = Table(summary_data, colWidths=[6*cm, 5*cm, 5*cm])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 10),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),
             [colors.HexColor("#f0f4ff"), colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
            ("ALIGN",       (1,0), (-1,-1), "CENTER"),
            ("PADDING",     (0,0), (-1,-1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5*cm))

        # ── Detection Analysis ────────────────────────────────────────────
        story.append(Paragraph("Detection Analysis", h1_style))
        story.append(Paragraph(
            f"Object detection breakdown for the last {hours} hours "
            f"across all configured classes.", body_style
        ))

        if by_class:
            det_data  = [["Class", "Detections", "% of Total"]]
            total     = sum(r["count"] for r in by_class)
            for row in by_class[:10]:
                pct = f"{row['count']/max(total,1)*100:.1f}%"
                det_data.append([
                    row["class_name"].title(),
                    f"{row['count']:,}",
                    pct
                ])
            det_table = Table(det_data, colWidths=[6*cm, 5*cm, 5*cm])
            det_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0f3460")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 10),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),
                 [colors.HexColor("#f0f8ff"), colors.white]),
                ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
                ("ALIGN",      (1,0), (-1,-1), "RIGHT"),
                ("PADDING",    (0,0), (-1,-1), 7),
            ]))
            story.append(det_table)
        else:
            story.append(Paragraph("No detections found for the specified period.", body_style))

        story.append(Spacer(1, 0.5*cm))

        # ── Alert Summary ────────────────────────────────────────────
        story.append(Paragraph("Alerts Summary", h1_style))
        alerts_data = analytics.alerts_by_type(hours)
        if alerts_data:
            a_data = [["Alert Type", "Count"]]
            for row in alerts_data:
                a_data.append([row["alert_type"].replace("_", " ").title(), str(row["count"])])
            a_table = Table(a_data, colWidths=[10*cm, 6*cm])
            a_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#b33939")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 10),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#fef0f0"), colors.white]),
                ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
                ("PADDING",    (0,0), (-1,-1), 7),
            ]))
            story.append(a_table)
        else:
            story.append(Paragraph("No alerts found for the specified period.", body_style))

        story.append(PageBreak())

        # ── Zone Analysis ────────────────────────────────────────────
        story.append(Paragraph("Zone Dwell Analysis", h1_style))
        zone_data = analytics.avg_dwell_per_zone(days=hours//24 if hours >= 24 else 1)
        if zone_data:
            z_data = [["Zone", "Avg Dwell (s)", "Max Dwell (s)", "Total Visits"]]
            for row in zone_data:
                z_data.append([
                    row["zone_name"], 
                    f"{row['avg_seconds']:.1f}", 
                    f"{row['max_seconds']:.1f}", 
                    str(row["visits"])
                ])
            z_table = Table(z_data, colWidths=[6*cm, 3.5*cm, 3.5*cm, 3*cm])
            z_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#218c74")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 10),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#f1fcf9"), colors.white]),
                ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
                ("PADDING",    (0,0), (-1,-1), 7),
                ("ALIGN",      (1,0), (-1,-1), "CENTER"),
            ]))
            story.append(z_table)
        else:
            story.append(Paragraph("No zone dwell data available.", body_style))
            
        story.append(Spacer(1, 0.5*cm))

        # ── Heatmap ────────────────────────────────────────────
        if heatmap_path and os.path.exists(heatmap_path):
            story.append(Paragraph("Activity Heatmap", h1_style))
            try:
                # Insert the heatmap image, scaling to fit the width
                img = Image(heatmap_path)
                img.drawWidth = 16*cm
                img.drawHeight = img.drawWidth * (img.imageHeight / max(img.imageWidth, 1))
                story.append(img)
            except Exception as e:
                logger.error(f"Failed to embed heatmap in PDF: {e}")
                story.append(Paragraph("Error loading heatmap image.", body_style))

        # Build Document
        doc.build(story)
        logger.info(f"PDF Report generated: {path}")
        return path
