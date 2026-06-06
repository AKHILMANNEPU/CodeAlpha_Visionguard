import pytest
import os
import sys
import numpy as np
import tracemalloc

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer3.storage_manager import StorageManager
from layer2.zone_intrusion import Zone
from layer4.notification_manager import NotificationManager

# =====================================================================
# 2. SOAK TESTING
# =====================================================================

def test_st_002_memory_leak_accelerated(tmp_path):
    """ST-002: 7-Day Memory Leak Detection (Accelerated).
    Processes 10,000 mock alerts to ensure Python gc reclaims objects.
    """
    tracemalloc.start()
    
    db_path = str(tmp_path / "soak.db")
    sm = StorageManager({"storage": {"db_path": db_path}})
    
    nm = NotificationManager(config={"email": {"enabled": False}})
    
    snapshot1 = tracemalloc.take_snapshot()
    
    # Simulate 10,000 events
    alerts_to_send = []
    for i in range(10000):
        sm.process({"tracks": [{"track_id": i, "bbox": [0,0,10,10], "center": [5,5], "confidence": 0.9, "class_name": "person"}]}, np.zeros((10,10,3), dtype=np.uint8))
        alerts_to_send.append({"type": "ZONE_ENTRY", "track_id": i})
        
        if len(alerts_to_send) >= 1000:
            nm.process_alerts(alerts_to_send) # clear queue
            alerts_to_send = []
            
    # clear rest
    if alerts_to_send:
        nm.process_alerts(alerts_to_send)
    
    snapshot2 = tracemalloc.take_snapshot()
    stats = snapshot2.compare_to(snapshot1, 'lineno')
    
    # Assert total difference is relatively small (under 10MB) to pass leak check
    total_diff_kb = sum(stat.size_diff for stat in stats) / 1024
    
    # Some DB caching is expected. Ensure it doesn't blow up linearly (e.g. < 10MB).
    assert total_diff_kb < 10000, f"Potential memory leak detected: {total_diff_kb} KB growth"
    tracemalloc.stop()
