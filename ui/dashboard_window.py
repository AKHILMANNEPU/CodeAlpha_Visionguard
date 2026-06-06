import logging
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QGridLayout, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

from layer5.detection_charts import DetectionBarChart, HourlyActivityChart
from layer5.alert_charts import AlertPieChart, AlertsPerHourChart
from layer5.line_trend_chart import LineCrossingTrendChart
from layer5.dwell_analytics import DwellAnalyticsPanel
from layer5.heatmap_viewer import HeatmapViewer

logger = logging.getLogger(__name__)

class DashboardWindow(QMainWindow):
    """
    Standalone Analytics Dashboard Window (Layer 5).
    """

    def __init__(self, dashboard_mgr, heatmap_generator, config: dict):
        super().__init__()
        self.dashboard_mgr = dashboard_mgr
        self.heatmap_generator = heatmap_generator
        self.config = config
        
        self.setWindowTitle("AI Analytics & Reporting Dashboard")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet("background-color: #0f0f0f; color: #e0e0e0;")

        self.last_heatmap_path = None

        self._build_ui()

        # Timer to refresh charts every 10 seconds
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_charts)
        self.refresh_timer.start(10000)

        # Timer to refresh live metrics fast (e.g. 500ms)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_live_metrics)
        self.metrics_timer.start(500)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)

        # ── Header & Export Row ──
        header_layout = QHBoxLayout()
        title = QLabel("Layer 5 — Intelligence Dashboard")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        header_layout.addWidget(title)
        
        header_layout.addStretch()

        btn_pdf = QPushButton("📄 Generate PDF Report")
        btn_excel = QPushButton("📊 Export Excel")
        
        for btn in [btn_pdf, btn_excel]:
            btn.setStyleSheet(
                "QPushButton { background: #2a2a2a; border: 1px solid #444; border-radius: 6px; padding: 10px 15px; font-weight: bold; font-size: 13px; }"
                "QPushButton:hover { background: #333; }"
            )
        
        btn_pdf.clicked.connect(self._export_pdf)
        btn_excel.clicked.connect(self._export_excel)

        header_layout.addWidget(btn_excel)
        header_layout.addWidget(btn_pdf)
        main_layout.addLayout(header_layout)

        # ── KPI Row ──
        kpi_frame = QFrame()
        kpi_frame.setStyleSheet("background: #1a1a1a; border-radius: 8px;")
        kpi_layout = QHBoxLayout(kpi_frame)
        
        self.kpi_labels = {}
        kpi_fields = [
            ("FPS", "fps"),
            ("Active Zones", "active_zones"),
            ("Total Objects", "object_count"),
            ("Alerts (1h)", "alerts_last_hour"),
            ("DB Size", "db_size_mb"),
            ("Uptime", "uptime_str")
        ]

        for label_text, key in kpi_fields:
            vbox = QVBoxLayout()
            lbl_title = QLabel(label_text)
            lbl_title.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_val = QLabel("0")
            lbl_val.setStyleSheet("color: #4FC3F7; font-size: 20px; font-weight: bold;")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_val)
            kpi_layout.addLayout(vbox)
            self.kpi_labels[key] = lbl_val

        main_layout.addWidget(kpi_frame)

        # ── Main Content Area ──
        content_layout = QHBoxLayout()
        
        # Left side: Tabs for Charts
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #333; border-radius: 4px; background: #111; }"
            "QTabBar::tab { background: #222; color: #aaa; padding: 8px 16px; border: 1px solid #333; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }"
            "QTabBar::tab:selected { background: #333; color: #fff; font-weight: bold; }"
        )

        # Tab 1: Detection Analytics
        det_tab = QWidget()
        det_layout = QVBoxLayout(det_tab)
        self.chart_det_bar = DetectionBarChart(self.dashboard_mgr.analytics, self.config)
        self.chart_det_line = HourlyActivityChart(self.dashboard_mgr.analytics, self.config)
        det_layout.addWidget(self.chart_det_bar)
        det_layout.addWidget(self.chart_det_line)
        self.tabs.addTab(det_tab, "Detections")

        # Tab 2: Alert Analytics
        alert_tab = QWidget()
        alert_layout = QHBoxLayout(alert_tab)
        self.chart_alert_pie = AlertPieChart(self.dashboard_mgr.analytics, self.config)
        self.chart_alert_bar = AlertsPerHourChart(self.dashboard_mgr.analytics, self.config)
        alert_layout.addWidget(self.chart_alert_pie)
        alert_layout.addWidget(self.chart_alert_bar)
        self.tabs.addTab(alert_tab, "Alerts")

        # Tab 3: Zone & Dwell
        zone_tab = QWidget()
        zone_layout = QVBoxLayout(zone_tab)
        self.panel_dwell = DwellAnalyticsPanel(self.dashboard_mgr.analytics, self.config)
        zone_layout.addWidget(self.panel_dwell)
        self.tabs.addTab(zone_tab, "Zone & Dwell")

        # Tab 4: Line Crossings
        line_tab = QWidget()
        line_layout = QVBoxLayout(line_tab)
        self.chart_line = LineCrossingTrendChart(self.dashboard_mgr.analytics, self.config)
        line_layout.addWidget(self.chart_line)
        self.tabs.addTab(line_tab, "Line Crossings")

        content_layout.addWidget(self.tabs, stretch=2)

        # Right side: Heatmap Viewer
        right_panel = QFrame()
        right_panel.setStyleSheet("background: #1a1a1a; border-radius: 8px;")
        right_layout = QVBoxLayout(right_panel)
        self.heatmap_viewer = HeatmapViewer(self.heatmap_generator, self.config)
        self.heatmap_viewer.save_requested.connect(self._on_heatmap_saved)
        right_layout.addWidget(self.heatmap_viewer)
        
        content_layout.addWidget(right_panel, stretch=1)

        main_layout.addLayout(content_layout, stretch=1)

    def update_live_metrics(self):
        metrics = self.dashboard_mgr.metrics_collector.current
        
        self.kpi_labels["fps"].setText(f"{metrics.fps}")
        self.kpi_labels["active_zones"].setText(f"{metrics.active_zones}")
        self.kpi_labels["object_count"].setText(f"{metrics.object_count}")
        self.kpi_labels["alerts_last_hour"].setText(f"{metrics.alerts_last_hour}")
        self.kpi_labels["db_size_mb"].setText(f"{metrics.db_size_mb} MB")
        self.kpi_labels["uptime_str"].setText(self.dashboard_mgr.metrics_collector.get_uptime_str())

    def update_heatmap_frame(self, frame):
        self.heatmap_viewer.set_latest_frame(frame)
        # We don't auto-refresh the heatmap here to save CPU. User clicks refresh in viewer.

    def refresh_charts(self):
        """Called by timer to pull new data for charts."""
        self.chart_det_bar.refresh()
        self.chart_det_line.refresh()
        self.chart_alert_pie.refresh()
        self.chart_alert_bar.refresh()
        self.panel_dwell.refresh()
        self.chart_line.refresh()

    def _on_heatmap_saved(self, path: str):
        self.last_heatmap_path = path

    def _export_pdf(self):
        try:
            path = self.dashboard_mgr.generate_pdf_report(hours=24, heatmap_path=self.last_heatmap_path)
            if path:
                QMessageBox.information(self, "Success", f"PDF Report saved successfully:\n{path}")
            else:
                QMessageBox.warning(self, "Error", "Failed to generate PDF. Check logs.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not generate PDF:\n{e}")

    def _export_excel(self):
        try:
            path = self.dashboard_mgr.generate_excel_report(hours=24)
            if path:
                QMessageBox.information(self, "Success", f"Excel Export saved successfully:\n{path}")
            else:
                QMessageBox.warning(self, "Error", "Failed to generate Excel. Check logs.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not generate Excel:\n{e}")
