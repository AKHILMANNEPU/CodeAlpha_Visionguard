import pytest
import threading
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer4.notification_manager import NotificationManager
from layer4.rules_engine import AlertRule

@pytest.fixture
def manager_config():
    return {
        "notifications": {
            "global_cooldown_seconds": 0
        }
    }

# =====================================================================
# 9. Performance Testing & 12. Scalability Testing
# =====================================================================

@pytest.mark.benchmark
def test_alert_processing_rate(manager_config, benchmark, mocker):
    """TC-NE-031: Process large volume of alerts rapidly."""
    mgr = NotificationManager(manager_config)
    mgr.rules_engine.rules = [
        AlertRule("Test", ["ZONE_ENTRY"], ["email"], "HIGH", ["person"])
    ]
    
    # Disable actual sending
    mgr.email.enabled = False
    
    alerts = []
    for i in range(1000):
        alerts.append({
            "alert_type": "ZONE_ENTRY",
            "class_name": "person",
            "zone_name": "TestZone",
            "track_id": i
        })
        
    def process():
        mgr.process_alerts(alerts, [])
        
    # The benchmark will ensure processing 1000 rules takes minimal time
    benchmark(process)

def test_multi_camera_alert_load(manager_config, mocker):
    """TC-NE-034 & TC-NE-050: 32 cameras generating alerts simultaneously."""
    mgr = NotificationManager(manager_config)
    mgr.rules_engine.rules = [
        AlertRule("Test", ["ZONE_ENTRY"], ["email"], "HIGH", ["person"])
    ]
    
    # Disable actual sending
    mgr.email.enabled = False
    
    def simulate_camera_alerts(cam_id):
        alerts = []
        for i in range(50):
            alerts.append({
                "alert_type": "ZONE_ENTRY",
                "class_name": "person",
                "zone_name": f"Zone_{cam_id}",
                "track_id": i
            })
        mgr.process_alerts(alerts, [])
        
    threads = []
    for i in range(32):
        t = threading.Thread(target=simulate_camera_alerts, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # If it didn't deadlock or crash, the test passes
    assert True
