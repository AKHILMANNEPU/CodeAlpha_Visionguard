import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt6.QtCharts  import (
    QChart, QChartView, QBarSeries,
    QBarSet, QBarCategoryAxis, QValueAxis
)
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QFont

from .detection_charts import (
    CHART_COLORS, _styled_chart, _styled_chart_view
)

logger = logging.getLogger(__name__)


class DwellAnalyticsPanel(QWidget):
    """
    Combined panel:
    Top half:    Table — zone, avg dwell, max dwell, visit count
    Bottom half: Bar chart — average dwell per zone
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        self.days      = config.get("dashboard", {}).get("dwell_days", 7)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Title
        title = QLabel(f"Dwell Time Analytics — Last {self.days} Days")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color:#e0e0e0; padding:4px;")
        layout.addWidget(title)

        # Stats table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Zone", "Avg Dwell", "Max Dwell", "Visits"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget{background:#111;color:#ddd;gridline-color:#333;"
            "border:1px solid #333;}"
            "QHeaderView::section{background:#1e1e1e;color:#aaa;padding:5px;"
            "border:none;border-bottom:1px solid #444;}"
            "QTableWidget::item:selected{background:#2a2a2a;}"
        )
        self.table.setMaximumHeight(200)
        layout.addWidget(self.table)

        # Bar chart — avg dwell per zone
        self.chart   = _styled_chart("Average Dwell Time per Zone (seconds)")
        self.bar_set = QBarSet("Avg Seconds")
        self.bar_set.setColor(QColor(CHART_COLORS[4]))
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
        self.axis_y.setTitleText("Seconds")
        self.axis_y.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_y)

        layout.addWidget(_styled_chart_view(self.chart))
        self.refresh()

    def refresh(self):
        try:
            data = self.analytics.avg_dwell_per_zone(self.days)

            # Update table
            self.table.setRowCount(0)
            for row_data in data:
                row = self.table.rowCount()
                self.table.insertRow(row)
                avg_str = f"{row_data['avg_seconds']:.1f}s"
                max_str = f"{row_data['max_seconds']:.1f}s"
                self.table.setItem(row, 0, QTableWidgetItem(
                    row_data["zone_name"]))
                self.table.setItem(row, 1, QTableWidgetItem(avg_str))
                self.table.setItem(row, 2, QTableWidgetItem(max_str))
                self.table.setItem(row, 3, QTableWidgetItem(
                    str(row_data["visits"])))

            # Update chart
            if not data:
                return
            self.bar_set.remove(0, self.bar_set.count())
            categories = []
            max_val    = 0
            for i, row_data in enumerate(data[:8]):
                self.bar_set.append(row_data["avg_seconds"])
                # Truncate long zone names
                label = row_data["zone_name"][:12]
                categories.append(label)
                max_val = max(max_val, row_data["avg_seconds"])

            self.axis_x.clear()
            self.axis_x.append(categories)
            self.axis_y.setRange(0, max_val * 1.2 if max_val > 0 else 60)
        except Exception as e:
            logger.debug(f"DwellAnalyticsPanel refresh error: {e}")
