import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.dashboard_window import DashboardWindow

@pytest.fixture
def mock_dashboard_mgr(mocker):
    mgr = mocker.MagicMock()
    # Mock analytics methods returning empty or dummy data
    mgr.analytics.get_detection_counts.return_value = {"person": 100, "vehicle": 50}
    mgr.analytics.get_hourly_activity.return_value = {12: 50, 13: 80}
    mgr.analytics.get_alert_breakdown.return_value = {"ZONE_ENTRY": 20}
    mgr.analytics.get_alerts_per_hour.return_value = {12: 10}
    mgr.analytics.get_dwell_stats.return_value = []
    mgr.analytics.get_line_crossings_trend.return_value = {"in": {}, "out": {}}
    
    mgr.metrics_collector.current = mocker.MagicMock()
    mgr.metrics_collector.current.fps = 30
    return mgr

@pytest.fixture
def mock_heatmap_gen(mocker):
    return mocker.MagicMock()

# =====================================================================
# 7. Dashboard Analytics Testing
# =====================================================================

def test_chart_refresh_logic(qtbot, mock_dashboard_mgr, mock_heatmap_gen, mocker):
    """UI-044 & UI-036: Chart Refresh triggers all analytics methods."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # We patch the chart refresh methods to spy on them
    spy_bar = mocker.spy(window.chart_det_bar, "refresh")
    spy_pie = mocker.spy(window.chart_alert_pie, "refresh")
    
    window.refresh_charts()
    
    spy_bar.assert_called_once()
    spy_pie.assert_called_once()

def test_chart_export_calls(qtbot, mock_dashboard_mgr, mock_heatmap_gen, mocker):
    """UI-045, UI-061, UI-062: Chart export triggers report generation."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # Mock the QMessageBox so it doesn't block
    mocker.patch("ui.dashboard_window.QMessageBox.information")
    mock_dashboard_mgr.generate_pdf_report.return_value = "/mock/path.pdf"
    
    window._export_pdf()
    
    mock_dashboard_mgr.generate_pdf_report.assert_called_once()
