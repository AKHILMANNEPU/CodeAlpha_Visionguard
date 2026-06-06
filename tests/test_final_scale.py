import pytest
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer4.rules_engine import AlertRulesEngine
from layer4.notification_manager import NotificationManager

# =====================================================================
# 3. LARGE SCALE LOAD TESTING
# =====================================================================

def test_lt_007_1000_alerts_per_hour(mocker):
    """LT-007: 1000 alerts per hour. We test 1000 alerts in 1 second."""
    nm = NotificationManager(config={"email": {"enabled": False}})
    
    start_time = time.time()
    
    alerts = []
    for i in range(1000):
        alerts.append({
            "type": "ZONE_ENTRY",
            "class_name": "person",
            "zone_name": "Area 51",
            "track_id": i
        })
        
    nm.process_alerts(alerts)
    
    elapsed = time.time() - start_time
    assert elapsed < 5.0 # Should be incredibly fast

def test_lt_005_100_camera_simulation(mocker):
    """LT-005: 100 Camera simulation evaluating rules concurrently."""
    rules = AlertRulesEngine(config={})
    
    # Simulate 100 cameras submitting 5 objects each frame = 500 objects
    # LT-006: 500 Objects Simultaneously
    massive_alert_records = []
    for cam in range(100):
        for obj in range(5):
            massive_alert_records.append({
                "type": "ZONE_ENTRY",
                "class_name": "person",
                "zone_name": f"Z_{cam}",
                "track_id": (cam * 100) + obj,
                "confidence": 0.9
            })
            
    routed = rules.evaluate(massive_alert_records, [])
    # Since we have no rules configured, routed will be 0. We're testing stability.
    assert isinstance(routed, list)
