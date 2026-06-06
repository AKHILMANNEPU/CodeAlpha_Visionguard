import logging
from typing import Dict, Any

from layer3.analytics import Analytics
from .live_metrics import LiveMetricsCollector
from .pdf_reporter import PDFReporter
from .excel_exporter import ExcelExporter

logger = logging.getLogger(__name__)

class DashboardManager:
    """
    Master controller for Layer 5 - Analytics Dashboard.
    Manages live metrics, interfaces with Layer 3 analytics,
    and coordinates report generation.
    """

    def __init__(self, config: dict, analytics: Analytics):
        logger.info("Initializing Layer 5 Dashboard Manager...")
        self.config = config
        self.analytics = analytics
        
        self.metrics_collector = LiveMetricsCollector(config)
        self.metrics_collector._analytics = self.analytics
        
        self.pdf_reporter = PDFReporter(config)
        self.excel_exporter = ExcelExporter(config)
        
        logger.info("Layer 5 Dashboard Manager ready.")

    def update_metrics(self, fps: float, tracks: list, line_counts: dict, density_levels: dict, alerts_fired: int, notifications: int):
        """Update live metrics. Called every frame from pipeline thread."""
        self.metrics_collector.update(
            fps=fps,
            tracks=tracks,
            line_counts=line_counts,
            density_levels=density_levels,
            alerts_fired=alerts_fired,
            notifications=notifications
        )

    def generate_pdf_report(self, hours: int = 24, heatmap_path: str = None) -> str:
        """Generate a PDF report."""
        return self.pdf_reporter.generate(
            analytics=self.analytics,
            hours=hours,
            heatmap_path=heatmap_path,
            camera_id=self.config.get("camera", {}).get("id", "cam_0")
        )

    def generate_excel_report(self, hours: int = 24) -> str:
        """Generate an Excel export."""
        return self.excel_exporter.generate(
            analytics=self.analytics,
            hours=hours,
            camera_id=self.config.get("camera", {}).get("id", "cam_0")
        )
