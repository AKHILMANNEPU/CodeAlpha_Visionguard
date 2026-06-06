import pytest
import sqlite3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer3.database import Database

@pytest.fixture
def temp_db_config(tmp_path):
    return {
        "storage": {
            "db_path": str(tmp_path / "test_failure.db"),
            "batch_size": 10
        }
    }

# =====================================================================
# G. Failure Testing & I. Recovery Testing
# =====================================================================

def test_database_restart_validation(temp_db_config):
    """TC-ST-010 & TC-ST-042: Restart application retains data."""
    # Instance 1
    db1 = Database(temp_db_config)
    alert_id = db1.save_alert(alert_type="test", message="Survive this")
    
    # Close instance 1 connection
    db1._conn.close()
    
    # Instance 2 (Application restarted)
    db2 = Database(temp_db_config)
    with db2._cursor() as cur:
        cur.execute("SELECT message FROM alerts WHERE id=?", (alert_id,))
        row = cur.fetchone()
        assert row["message"] == "Survive this"

def test_sqlite_corruption_handling(temp_db_config):
    """TC-ST-035: Corrupt the database file explicitly."""
    db1 = Database(temp_db_config)
    db1.save_alert(alert_type="test", message="Before corruption")
    db1._conn.close()
    
    # Corrupt the file
    db_path = temp_db_config["storage"]["db_path"]
    with open(db_path, "wb") as f:
        f.write(b"this is completely corrupted nonsense data")
        
    # App starts up and encounters corrupted DB
    # Should raise database error
    with pytest.raises(sqlite3.DatabaseError):
        db2 = Database(temp_db_config)

def test_disk_write_error_handling(temp_db_config, monkeypatch):
    """TC-ST-033: Simulate a disk full or read-only error."""
    db = Database(temp_db_config)
    
    # Mock the execute method to throw an OperationalError (Disk Full)
    def mock_execute(*args, **kwargs):
        raise sqlite3.OperationalError("database or disk is full")
        
    # We monkeypatch the context manager to yield a mock cursor that raises error
    class MockCursor:
        def execute(self, *args, **kwargs):
            mock_execute()
        def close(self):
            pass
            
    def mock_cursor_ctx(self):
        class Ctx:
            def __enter__(self):
                return MockCursor()
            def __exit__(self, exc_type, exc_val, exc_tb):
                return False
        return Ctx()
        
    monkeypatch.setattr(Database, "_cursor", mock_cursor_ctx)
    
    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        db.save_alert(alert_type="test", message="Will fail")
