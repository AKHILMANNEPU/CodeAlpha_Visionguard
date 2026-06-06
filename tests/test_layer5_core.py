import pytest
import os
import sys
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.dashboard_window import DashboardWindow

@pytest.fixture
def mock_dashboard_mgr(mocker):
    mgr = mocker.MagicMock()
    mgr.analytics = mocker.MagicMock()
    mgr.metrics_collector = mocker.MagicMock()
    mgr.metrics_collector.current = mocker.MagicMock()
    mgr.metrics_collector.current.fps = 30
    mgr.metrics_collector.current.active_zones = 2
    mgr.metrics_collector.current.object_count = 5
    mgr.metrics_collector.current.alerts_last_hour = 12
    mgr.metrics_collector.current.db_size_mb = 100
    mgr.metrics_collector.get_uptime_str.return_value = "01:00:00"
    return mgr

@pytest.fixture
def mock_heatmap_gen(mocker):
    return mocker.MagicMock()

# =====================================================================
# 3. Functional Testing (Core UI)
# =====================================================================

def test_application_launch(qtbot, mock_dashboard_mgr, mock_heatmap_gen):
    """UI-001 & UI-003: App launch and dashboard load"""
    config = {}
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, config)
    qtbot.addWidget(window)
    
    # Assert window is successfully created and has title
    assert window.windowTitle() == "AI Analytics & Reporting Dashboard"
    # Ensure minimum size is set
    assert window.minimumSize().width() == 1200
    assert window.minimumSize().height() == 800

def test_navigation_and_tabs(qtbot, mock_dashboard_mgr, mock_heatmap_gen):
    """UI-004: Tabs navigation."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # Check that tabs are present
    assert window.tabs.count() == 4
    assert window.tabs.tabText(0) == "Detections"
    assert window.tabs.tabText(1) == "Alerts"
    assert window.tabs.tabText(2) == "Zone & Dwell"
    assert window.tabs.tabText(3) == "Line Crossings"

def test_kpi_metrics_update(qtbot, mock_dashboard_mgr, mock_heatmap_gen):
    """UI-036 to UI-042: Verify KPI panels pull from metrics collector."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # Trigger the update manually
    window.update_live_metrics()
    
    # Verify the mocked data propagated to labels
    assert window.kpi_labels["fps"].text() == "30"
    assert window.kpi_labels["active_zones"].text() == "2"
    assert window.kpi_labels["object_count"].text() == "5"

def test_window_resize(qtbot, mock_dashboard_mgr, mock_heatmap_gen):
    """UI-005 & UI-071: Rapid resizing shouldn't crash."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    window.resize(1400, 900)
    assert window.size().width() == 1400
    
    window.resize(1920, 1080)
    assert window.size().height() == 1080
