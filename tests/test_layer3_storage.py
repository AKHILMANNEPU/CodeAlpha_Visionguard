import pytest
import sqlite3
import os
import shutil
import numpy as np
from datetime import datetime
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer3.database import Database
from layer3.clip_storage import ClipStorage

@pytest.fixture
def temp_db_config(tmp_path):
    return {
        "storage": {
            "db_path": str(tmp_path / "test_detections.db"),
            "batch_size": 10
        }
    }

@pytest.fixture
def temp_clip_config(tmp_path):
    return {
        "storage": {
            "clips_dir": str(tmp_path / "clips"),
            "snapshots_dir": str(tmp_path / "snapshots"),
            "clip_pre_seconds": 2,
            "clip_post_seconds": 2,
            "clip_fps": 10
        }
    }

# =====================================================================
# A. Functional Testing & B. Database Integrity
# =====================================================================

def test_create_detection_event(temp_db_config):
    db = Database(temp_db_config)
    track = {
        "track_id": 99,
        "class_name": "person",
        "class_id": 0,
        "confidence": 0.95,
        "bbox": [10, 20, 30, 40],
        "center": [20, 30]
    }
    
    # Needs a flush since batch_size is 10
    db.buffer_detection(track)
    db.flush_detections()
    
    with db._cursor() as cur:
        cur.execute("SELECT * FROM detections WHERE track_id = 99")
        row = cur.fetchone()
        
        assert row is not None
        assert row["class_name"] == "person"
        assert row["confidence"] == 0.95
        assert row["cx"] == 20

def test_store_multiple_events_batching(temp_db_config):
    # batch_size is 10 in fixture
    db = Database(temp_db_config)
    
    # Insert 100 events
    for i in range(100):
        track = {
            "track_id": i,
            "class_name": "vehicle",
            "confidence": 0.8,
            "bbox": [0,0,10,10],
            "center": [5,5]
        }
        db.buffer_detection(track)
        
    db.flush_detections()
    
    with db._cursor() as cur:
        cur.execute("SELECT count(*) FROM detections")
        count = cur.fetchone()[0]
        assert count == 100

def test_timestamp_validation(temp_db_config):
    db = Database(temp_db_config)
    now_utc = datetime.utcnow()
    alert_id = db.save_alert(alert_type="zone_entry", message="Test")
    
    with db._cursor() as cur:
        cur.execute("SELECT timestamp FROM alerts WHERE id=?", (alert_id,))
        row = cur.fetchone()
        saved_time = datetime.fromisoformat(row["timestamp"])
        
        # Check if saved time is within 5 seconds of our `now_utc`
        diff = abs((saved_time - now_utc).total_seconds())
        assert diff < 5

def test_null_value_validation(temp_db_config):
    db = Database(temp_db_config)
    with db._cursor() as cur:
        with pytest.raises(sqlite3.IntegrityError):
            # Attempt to insert NULL into NOT NULL timestamp
            cur.execute("INSERT INTO alerts (timestamp, alert_type, message) VALUES (NULL, 'x', 'x')")

# =====================================================================
# C. Video Clip Generation & D. Buffered Frame Testing
# =====================================================================

def test_circular_buffer_overflow(temp_clip_config):
    storage = ClipStorage(temp_clip_config)
    
    # Buffer maxlen = pre_seconds (2) * fps (10) = 20
    assert storage._ring_buffer.maxlen == 20
    
    # Feed 25 frames
    for i in range(25):
        frame = np.ones((10, 10, 3), dtype=np.uint8) * i
        storage.update(frame)
        
    # The length should be capped at 20
    assert len(storage._ring_buffer) == 20
    
    # The oldest frames (0,1,2,3,4) should be discarded. The oldest now is 5.
    oldest_frame = storage._ring_buffer[0]
    assert oldest_frame[0,0,0] == 5

# =====================================================================
# H. Security Testing
# =====================================================================

def test_sql_injection_prevention(temp_db_config):
    db = Database(temp_db_config)
    # Attempt SQL injection through a message string
    malicious_string = "Test'; DROP TABLE alerts; --"
    
    alert_id = db.save_alert(alert_type="test", message=malicious_string)
    
    with db._cursor() as cur:
        # If it was injected, alerts might not exist or the message would be truncated
        cur.execute("SELECT message FROM alerts WHERE id=?", (alert_id,))
        row = cur.fetchone()
        
        # Parameterized queries treat it as literal string
        assert row["message"] == malicious_string
        
        # Verify table still exists
        cur.execute("SELECT count(*) FROM alerts")
        assert cur.fetchone() is not None

def test_path_traversal_attack(temp_db_config):
    # Tests that the application correctly sanitizes or accepts safe paths,
    # and whether the DB allows inserting it as a string (it shouldn't execute paths).
    db = Database(temp_db_config)
    malicious_path = "../../system32/cmd.exe"
    alert_id = db.save_alert(alert_type="test", message="Test", snapshot_path=malicious_path)
    
    with db._cursor() as cur:
        cur.execute("SELECT snapshot_path FROM alerts WHERE id=?", (alert_id,))
        row = cur.fetchone()
        assert row["snapshot_path"] == malicious_path

# =====================================================================
# I. Recovery Testing
# =====================================================================

def test_missing_storage_directory(tmp_path):
    config = {"storage": {"db_path": str(tmp_path / "missing_dir" / "test.db")}}
    
    # Should not raise FileNotFoundError, it should create the dir
    db = Database(config)
    assert os.path.exists(str(tmp_path / "missing_dir"))
    assert os.path.exists(str(tmp_path / "missing_dir" / "test.db"))
