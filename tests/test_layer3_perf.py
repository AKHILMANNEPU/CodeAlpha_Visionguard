import pytest
import sqlite3
import os
import threading
import time
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer3.database import Database

@pytest.fixture
def temp_db_config(tmp_path):
    return {
        "storage": {
            "db_path": str(tmp_path / "test_perf.db"),
            "batch_size": 500  # optimize for massive inserts
        }
    }

# =====================================================================
# E. Performance Testing & F. Stress Testing
# =====================================================================

@pytest.mark.benchmark
def test_high_event_rate_insertion(temp_db_config, benchmark):
    """TC-ST-021: Insert 1000 events as fast as possible."""
    db = Database(temp_db_config)
    
    def insert_1000():
        for i in range(1000):
            track = {
                "track_id": i,
                "class_name": "person",
                "confidence": 0.99,
                "bbox": [10, 10, 20, 20],
                "center": [15, 15]
            }
            db.buffer_detection(track)
        db.flush_detections()
        
    benchmark(insert_1000)
    
    with db._cursor() as cur:
        cur.execute("SELECT count(*) FROM detections")
        # Since benchmark runs it multiple times, it will be multiple of 1000
        assert cur.fetchone()[0] >= 1000

def test_large_database_query_speed(temp_db_config):
    """TC-ST-023: Insert 50,000 records and query them under 2 seconds."""
    db = Database(temp_db_config)
    
    # Pre-fill database
    for i in range(50_000):
        track = {
            "track_id": i % 100,
            "class_name": "vehicle",
            "confidence": 0.8,
            "bbox": [1, 1, 2, 2],
            "center": [1, 1]
        }
        db.buffer_detection(track)
    db.flush_detections()
    
    start_time = time.time()
    
    with db._cursor() as cur:
        cur.execute("SELECT * FROM detections WHERE class_name = 'vehicle' LIMIT 10000")
        rows = cur.fetchall()
        
    end_time = time.time()
    duration = end_time - start_time
    
    assert len(rows) == 10000
    assert duration < 2.0  # Must be faster than 2 seconds

# =====================================================================
# J. Scalability Testing (Multi-Camera Threading)
# =====================================================================

def test_multi_camera_concurrent_writes(temp_db_config):
    """TC-ST-044 to TC-ST-048: 16 Cameras simulated."""
    db = Database(temp_db_config)
    num_cameras = 16
    events_per_cam = 1000
    
    def camera_simulation(cam_id: str):
        for i in range(events_per_cam):
            track = {
                "track_id": i,
                "class_name": "person",
                "confidence": 0.9,
                "bbox": [0,0,10,10],
                "center": [5,5]
            }
            db.buffer_detection(track, camera_id=cam_id)
        db.flush_detections()
        
    threads = []
    for i in range(num_cameras):
        t = threading.Thread(target=camera_simulation, args=(f"cam_{i}",))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Verify all records made it to DB without deadlock or corruption
    with db._cursor() as cur:
        cur.execute("SELECT count(*) FROM detections")
        total = cur.fetchone()[0]
        assert total == (num_cameras * events_per_cam)
