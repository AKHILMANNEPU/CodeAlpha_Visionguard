import logging
from typing import List, Dict
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCharts  import (
    QChart, QChartView, QBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis,
    QLineSeries, QDateTimeAxis, QSplineSeries
)
from PyQt6.QtCore    import Qt, QDateTime
from PyQt6.QtGui     import QPainter, QColor, QFont

logger = logging.getLogger(__name__)


# Color palette for charts — professional dark theme
CHART_COLORS = [
    "#4FC3F7", "#81C784", "#FFB74D", "#E57373",
    "#CE93D8", "#4DB6AC", "#F06292", "#AED581"
]


def _styled_chart(title: str) -> QChart:
    """Create a dark-themed QChart."""
    chart = QChart()
    chart.setTitle(title)
    chart.setTitleFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
    chart.setBackgroundBrush(QColor("#1a1a1a"))
    chart.setTitleBrush(QColor("#e0e0e0"))
    chart.setPlotAreaBackgroundBrush(QColor("#111111"))
    chart.setPlotAreaBackgroundVisible(True)
    chart.legend().setLabelColor(QColor("#cccccc"))
    chart.legend().setBackgroundVisible(False)
    chart.setMargins(chart.margins())
    chart.setDropShadowEnabled(False)
    return chart


def _styled_chart_view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet("background: #1a1a1a; border: none;")
    return view


class DetectionBarChart(QWidget):
    """
    Horizontal bar chart showing detection counts per object class.
    Updates every refresh_interval seconds from SQLite.
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        cfg            = config.get("dashboard", {})
        self.hours     = cfg.get("chart_hours", 24)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart    = _styled_chart(f"Detections by Class (Last {self.hours}h)")
        self.bar_set  = QBarSet("Count")
        self.bar_set.setColor(QColor(CHART_COLORS[0]))

        self.series   = QBarSeries()
        self.series.append(self.bar_set)
        self.chart.addSeries(self.series)

        self.axis_x   = QBarCategoryAxis()
        self.axis_x.setLabelsColor(QColor("#aaaaaa"))
        self.axis_x.setGridLineColor(QColor("#333333"))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.series.attachAxis(self.axis_x)

        self.axis_y   = QValueAxis()
        self.axis_y.setLabelsColor(QColor("#aaaaaa"))
        self.axis_y.setGridLineColor(QColor("#333333"))
        self.axis_y.setTitleText("Count")
        self.axis_y.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_y)

        layout.addWidget(_styled_chart_view(self.chart))
        self.refresh()

    def refresh(self):
        """Pull latest data from SQLite and redraw."""
        try:
            data = self.analytics.detections_by_class(self.hours)
            if not data:
                return

            self.bar_set.remove(0, self.bar_set.count())
            categories = []

            for i, row in enumerate(data[:8]):   # top 8 classes
                self.bar_set.append(row["count"])
                categories.append(row["class_name"].title())
                # Color each bar differently
                self.bar_set.setColor(QColor(CHART_COLORS[i % len(CHART_COLORS)]))

            self.axis_x.clear()
            self.axis_x.append(categories)

            max_val = max(r["count"] for r in data[:8]) if data else 10
            self.axis_y.setRange(0, max_val * 1.1)
        except Exception as e:
            logger.debug(f"DetectionBarChart refresh error: {e}")


class HourlyActivityChart(QWidget):
    """
    Spline line chart showing detection count per hour.
    Last 24 hours by default.
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        cfg            = config.get("dashboard", {})
        self.days      = cfg.get("hourly_chart_days", 1)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart  = _styled_chart("Hourly Activity (Last 24h)")
        self.series = QSplineSeries()
        self.series.setName("Detections")
        self.series.setColor(QColor(CHART_COLORS[0]))
        pen = self.series.pen()
        pen.setWidth(2)
        self.series.setPen(pen)
        self.chart.addSeries(self.series)

        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm")
        self.axis_x.setLabelsColor(QColor("#aaaaaa"))
        self.axis_x.setGridLineColor(QColor("#333333"))
        self.axis_x.setTitleText("Time")
        self.axis_x.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.series.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setLabelsColor(QColor("#aaaaaa"))
        self.axis_y.setGridLineColor(QColor("#333333"))
        self.axis_y.setTitleText("Detections")
        self.axis_y.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_y)

        layout.addWidget(_styled_chart_view(self.chart))
        self.refresh()

    def refresh(self):
        try:
            from datetime import datetime
            data = self.analytics.detections_per_hour(self.days)
            if not data:
                return

            self.series.clear()
            values = []
            for row in data:
                try:
                    dt  = datetime.strptime(row["hour"], "%Y-%m-%d %H")
                    qdt = QDateTime(dt.year, dt.month, dt.day,
                                    dt.hour, 0, 0)
                    self.series.append(qdt.toMSecsSinceEpoch(), row["count"])
                    values.append(row["count"])
                except Exception:
                    continue

            if values:
                self.axis_y.setRange(0, max(values) * 1.15)
        except Exception as e:
            logger.debug(f"HourlyActivityChart refresh error: {e}")
