import logging
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel
from PyQt6.QtCharts  import (
    QChart, QChartView, QLineSeries,
    QDateTimeAxis, QValueAxis
)
from PyQt6.QtCore    import Qt, QDateTime
from PyQt6.QtGui     import QPainter, QColor

from .detection_charts import _styled_chart, _styled_chart_view, CHART_COLORS

logger = logging.getLogger(__name__)


class LineCrossingTrendChart(QWidget):
    """
    Dual-line chart showing IN vs OUT crossings over time.
    Has a dropdown to select which tripline to display.
    """

    def __init__(self, analytics, config: dict, parent=None):
        super().__init__(parent)
        self.analytics   = analytics
        self.current_line= None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Line selector dropdown
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Line:"))
        self.line_combo = QComboBox()
        self.line_combo.setStyleSheet(
            "QComboBox{background:#222;color:#ddd;border:1px solid #444;"
            "border-radius:4px;padding:4px;}"
        )
        self.line_combo.currentTextChanged.connect(self._on_line_changed)
        top_row.addWidget(self.line_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Chart
        self.chart    = _styled_chart("Line Crossing — IN vs OUT (24h)")
        self.series_in  = QLineSeries()
        self.series_out = QLineSeries()
        self.series_in.setName("Entering")
        self.series_out.setName("Exiting")
        self.series_in.setColor(QColor(CHART_COLORS[1]))   # green
        self.series_out.setColor(QColor(CHART_COLORS[3]))  # red

        for s in [self.series_in, self.series_out]:
            pen = s.pen()
            pen.setWidth(2)
            s.setPen(pen)
            self.chart.addSeries(s)

        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm")
        self.axis_x.setLabelsColor(QColor("#aaaaaa"))
        self.axis_x.setGridLineColor(QColor("#333333"))
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.series_in.attachAxis(self.axis_x)
        self.series_out.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setLabelsColor(QColor("#aaaaaa"))
        self.axis_y.setGridLineColor(QColor("#333333"))
        self.axis_y.setTitleText("Crossings")
        self.axis_y.setTitleBrush(QColor("#888888"))
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series_in.attachAxis(self.axis_y)
        self.series_out.attachAxis(self.axis_y)

        layout.addWidget(_styled_chart_view(self.chart))
        self._load_line_names()

    def _load_line_names(self):
        """Populate dropdown from database."""
        try:
            rows = self.analytics._query(
                "SELECT DISTINCT line_name FROM line_events ORDER BY line_name"
            )
            for row in rows:
                self.line_combo.addItem(row["line_name"])
        except Exception:
            pass

    def _on_line_changed(self, name: str):
        self.current_line = name
        self.refresh()

    def refresh(self):
        if not self.current_line:
            return
        try:
            data = self.analytics.line_crossings_over_time(
                self.current_line, days=1
            )
            if not data:
                return

            self.series_in.clear()
            self.series_out.clear()
            all_vals = []

            for row in data:
                try:
                    dt  = datetime.strptime(row["hour"], "%Y-%m-%d %H")
                    ms  = QDateTime(dt.year, dt.month, dt.day,
                                    dt.hour, 0, 0).toMSecsSinceEpoch()
                    self.series_in.append(ms,  row.get("entering", 0))
                    self.series_out.append(ms, row.get("exiting",  0))
                    all_vals.extend([row.get("entering", 0),
                                     row.get("exiting", 0)])
                except Exception:
                    continue

            if all_vals:
                self.axis_y.setRange(0, max(all_vals) * 1.2)
        except Exception as e:
            logger.debug(f"LineCrossingTrendChart refresh error: {e}")
