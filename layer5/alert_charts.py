import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame
)
from PyQt6.QtCharts  import (
    QChart, QChartView, QPieSeries,
    QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis
)
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QFont

from .detection_charts import CHART_COLORS, _styled_chart, _styled_chart_view

logger = logging.getLogger(__name__)


class AlertPieChart(QWidget):
    """
    Pie chart showing distribution of alert types.
    e.g. 40% Zone Entry, 30% Dwell, 20% Crowd, 10% Line Cross
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        self.hours     = config.get("dashboard", {}).get("chart_hours", 24)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart  = _styled_chart(f"Alert Types (Last {self.hours}h)")
        self.series = QPieSeries()

        # Style slices
        self.series.setHoleSize(0.35)       # donut style
        self.chart.addSeries(self.series)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(_styled_chart_view(self.chart))
        self.refresh()

    def refresh(self):
        try:
            data = self.analytics.alerts_by_type(self.hours)
            if not data:
                return

            self.series.clear()
            for i, row in enumerate(data):
                label = row["alert_type"].replace("_", " ").title()
                slc   = self.series.append(f"{label}\n{row['count']}", row["count"])
                slc.setColor(QColor(CHART_COLORS[i % len(CHART_COLORS)]))
                slc.setLabelVisible(True)
                slc.setLabelColor(QColor("#e0e0e0"))
                slc.setBorderColor(QColor("#333333"))
        except Exception as e:
            logger.debug(f"AlertPieChart refresh error: {e}")


class AlertsPerHourChart(QWidget):
    """
    Bar chart: alerts per hour over last 24h.
    Highlights hours with HIGH alert activity.
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chart   = _styled_chart("Alerts per Hour (Last 24h)")
        self.bar_set = QBarSet("Alerts")
        self.bar_set.setColor(QColor("#E57373"))
        self.series  = QBarSeries()
        self.series.append(self.bar_set)
        self.chart.addSeries(self.series)

        self.axis_x = QBarCategoryAxis()
        self.axis_x.setLabelsColor(QColor("#aaaaaa"))
        self.axis_x.setGridLineColor(QColor("#333333"))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.series.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setLabelsColor(QColor("#aaaaaa"))
        self.axis_y.setGridLineColor(QColor("#333333"))
        self.axis_y.setTitleText("Alerts")
        self.axis_y.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_y)

        layout.addWidget(_styled_chart_view(self.chart))
        self.refresh()

    def refresh(self):
        try:
            data = self.analytics.alerts_per_hour(days=1)
            if not data:
                return

            self.bar_set.remove(0, self.bar_set.count())
            categories = []
            for row in data:
                hour = row["hour"][-5:]   # "HH:00"
                self.bar_set.append(row["count"])
                categories.append(hour)

            self.axis_x.clear()
            self.axis_x.append(categories)
            max_val = max(r["count"] for r in data) if data else 1
            self.axis_y.setRange(0, max_val * 1.2)
        except Exception as e:
            logger.debug(f"AlertsPerHourChart refresh error: {e}")
