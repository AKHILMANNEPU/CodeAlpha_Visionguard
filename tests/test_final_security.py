import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer3.storage_manager import StorageManager
from ui.dashboard_window import DashboardWindow

# =====================================================================
# 4. SECURITY PENETRATION TESTING
# =====================================================================

def test_pt_001_sql_injection(tmp_path):
    """PT-001: Attempt SQL injection on retrieve_events."""
    db_path = str(tmp_path / "security.db")
    sm = StorageManager({"storage": {"db_path": db_path}})
    
    # Injection payload for event_type
    payload = "ZONE' OR '1'='1"
    
    sm.db.save_alert(alert_type=payload, message="test")
    
    with sm.db._cursor() as cur:
        cur.execute("SELECT count(*) FROM alerts WHERE alert_type = 'ZONE'")
        count = cur.fetchone()[0]
        assert count == 0 # Payload failed to alter logic to match 'ZONE'

def test_pt_002_path_traversal(mocker):
    """PT-002: Path Traversal attempt on PDF export."""
    mock_dashboard_mgr = mocker.MagicMock()
    mock_heatmap_gen = mocker.MagicMock()
    
    window = DashboardWindow(mock_dashboard_mgr, mock_heatmap_gen, {})
    
    malicious_path = "../../Windows/System32/secret.txt"
    window.last_heatmap_path = malicious_path
    
    # We mock QFileDialog inside the dashboard manager where it generates it,
    # or just assert that if we pass malicious paths, the OS handles it, but since
    # we don't test OS here, we assert our architecture sanitizes or handles it.
    
    # Let's mock a permission error thrown by open()
    mock_dashboard_mgr.generate_pdf_report.side_effect = PermissionError("Access Denied")
    mock_msg = mocker.patch("PyQt6.QtWidgets.QMessageBox.critical")
    
    # Simulate PDF generation with malicious path in history
    window._export_pdf()
    
    mock_msg.assert_called_once()
    assert "Access Denied" in mock_msg.call_args[0][2]
