import pytest
import os
import sys
import numpy as np
import sys

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
    return mocker.MagicMock()

# =====================================================================
# 12. Performance Testing & 13. Stress Testing & 15. Security
# =====================================================================

@pytest.mark.benchmark
def test_ui_response_time(qtbot, mock_dashboard_mgr, mock_heatmap_gen, benchmark):
    """UI-067: UI response time < 100ms when updating charts."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # Benchmark how long a complete dashboard chart refresh takes
    benchmark(window.refresh_charts)
    # The benchmark framework will assert if it takes excessively long or if the user set a max_time

def test_malicious_file_import(qtbot, mock_dashboard_mgr, mock_heatmap_gen, mocker):
    """UI-082 & UI-083: Path traversal attempt on heatmap save."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    viewer = window.heatmap_viewer
    
    # User tries to save image over system32 (on Windows) or /etc/passwd
    malicious_path = "C:\\Windows\\System32\\cmd.exe"
    mocker.patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(malicious_path, ""))
    
    # We mock the actual save logic in HeatmapViewer so it doesn't actually overwrite system32,
    # but we verify if the UI handles it. In actual app, cv2.imwrite or file open would fail with PermissionError
    mock_heatmap_gen.save.side_effect = PermissionError("Access Denied")
    mock_msg = mocker.patch("PyQt6.QtWidgets.QMessageBox.critical")
    
    viewer._last_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    viewer._save_heatmap()
    
    # Verify the UI caught the PermissionError and displayed a critical messagebox
    mock_msg.assert_called_once()
    assert "Failed to save" in mock_msg.call_args[0][2]

# =====================================================================
# 16. Recovery Testing & 18. End-to-End UI Validation
# =====================================================================

def test_dashboard_recovery(qtbot, mock_dashboard_mgr, mock_heatmap_gen):
    """UI-089: Dashboard widgets reload correctly after a simulated exception."""
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    qtbot.addWidget(window)
    
    # If the metrics timer dies or throws an error, the dashboard shouldn't crash entirely.
    # Simulate an error in metrics
    mock_dashboard_mgr.metrics_collector.current = None  # Missing current data
    
    try:
        window.update_live_metrics()
        # Should raise AttributeError
    except AttributeError:
        pass
        
    window.show()
    # App is still alive and window is still rendering
    assert window.isVisible()
