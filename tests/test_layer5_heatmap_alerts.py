import pytest
import os
import sys
import numpy as np
from PyQt6.QtCore import Qt
import sys
from PyQt6.QtCore import Qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.dashboard_window import DashboardWindow

@pytest.fixture
def mock_dashboard_mgr(mocker):
    mgr = mocker.MagicMock()
    mgr.analytics = mocker.MagicMock()
    mgr.metrics_collector.current = mocker.MagicMock()
    return mgr

@pytest.fixture
def mock_heatmap_gen(mocker):
    gen = mocker.MagicMock()
    gen.get_heatmap.return_value = None  # return None or dummy image
    return gen

# =====================================================================
# 8. Heatmap Testing & 9. Alert Monitoring Testing
# =====================================================================

def test_generate_heatmap(qtbot, mock_dashboard_mgr, mock_heatmap_gen, mocker):
    """UI-046 & UI-048: Heatmap triggers generation and updates UI."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    viewer = window.heatmap_viewer
    viewer.set_latest_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    
    # HeatmapViewer doesn't have a btn_refresh, so we call the method directly
    viewer.refresh()
    
    # Assert generator was called
    mock_heatmap_gen.render.assert_called_once()
    
def test_heatmap_export(qtbot, mock_dashboard_mgr, mock_heatmap_gen, mocker):
    """UI-050: Heatmap exported successfully."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    viewer = window.heatmap_viewer
    
    mocker.patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=("/mock/heat.png", ""))
    mocker.patch("PyQt6.QtWidgets.QMessageBox.information")
    
    # Simulate save
    viewer._last_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    viewer._save_heatmap()
    
    # The last_heatmap_path on dashboard should be updated via signal
    assert window.last_heatmap_path == "/mock/heat.png"
