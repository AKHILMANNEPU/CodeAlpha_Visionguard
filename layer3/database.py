import sqlite3
import threading
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """
    SQLite database for all structured detection data.

    Why SQLite over PostgreSQL for desktop:
    - Zero installation — built into Python
    - Single file database — easy to backup, share, delete
    - Handles millions of detection records easily
    - No server process needed
    - Thread-safe with check_same_thread=False + lock

    Tables:
        detections    → every tracked object per frame (sampled)
        alerts        → every alert fired by Layer 2
        line_events   → every line crossing event
        dwell_events  → zone dwell time records
        system_logs   → app start/stop, errors, camera status
    """

    def __init__(self, config: dict):
        cfg      = config.get("storage", {})
        db_path  = cfg.get("db_path", "data/detections.db")

        # Create data directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path    = db_path
        self._lock      = threading.Lock()
        self._conn      = None
        self._batch     = []                     # write buffer
        self._batch_size= cfg.get("batch_size", 50)  # flush every N records

        self._connect()
        self._create_schema()
        logger.info(f"SQLite database ready: {db_path}")

    def _connect(self):
        """Open SQLite connection. check_same_thread=False needed for PyQt6 threads."""
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,   # we handle thread safety ourselves
            timeout=10
        )
        # Performance pragmas — safe for desktop use
        self._conn.execute("PRAGMA journal_mode=WAL")    # write-ahead logging
        self._conn.execute("PRAGMA synchronous=NORMAL")  # faster writes
        self._conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row             # dict-like rows

    @contextmanager
    def _cursor(self):
        """Thread-safe cursor context manager."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                yield cursor
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                logger.error(f"Database error: {e}")
                raise
            finally:
                cursor.close()

    def _create_schema(self):
        """Create all tables if they don't exist."""
        with self._cursor() as cur:

            # ── Detections table ─────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    camera_id   TEXT    NOT NULL DEFAULT 'cam_0',
                    track_id    INTEGER NOT NULL,
                    class_name  TEXT    NOT NULL,
                    class_id    INTEGER NOT NULL,
                    confidence  REAL    NOT NULL,
                    x1          INTEGER NOT NULL,
                    y1          INTEGER NOT NULL,
                    x2          INTEGER NOT NULL,
                    y2          INTEGER NOT NULL,
                    cx          INTEGER NOT NULL,
                    cy          INTEGER NOT NULL,
                    action      TEXT,
                    zones       TEXT,        -- JSON array of zone names
                    frame_num   INTEGER
                )
            """)

            # Index for fast time-range queries
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detections_timestamp
                ON detections(timestamp)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detections_class
                ON detections(class_name)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_detections_camera
                ON detections(camera_id)
            """)

            # ── Alerts table ──────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp    TEXT    NOT NULL,
                    camera_id    TEXT    NOT NULL DEFAULT 'cam_0',
                    alert_type   TEXT    NOT NULL,
                    message      TEXT    NOT NULL,
                    track_id     INTEGER,
                    class_name   TEXT,
                    zone_name    TEXT,
                    snapshot_path TEXT,       -- JPEG snapshot of the frame
                    clip_path    TEXT,        -- video clip path
                    acknowledged INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
                ON alerts(timestamp)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_type
                ON alerts(alert_type)
            """)

            # ── Line crossing events ──────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS line_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    camera_id   TEXT    NOT NULL DEFAULT 'cam_0',
                    line_name   TEXT    NOT NULL,
                    direction   TEXT    NOT NULL,   -- 'in' or 'out'
                    track_id    INTEGER NOT NULL,
                    class_name  TEXT    NOT NULL,
                    running_in  INTEGER NOT NULL DEFAULT 0,
                    running_out INTEGER NOT NULL DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_line_events_timestamp
                ON line_events(timestamp)
            """)

            # ── Dwell events ──────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dwell_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    camera_id       TEXT    NOT NULL DEFAULT 'cam_0',
                    track_id        INTEGER NOT NULL,
                    class_name      TEXT    NOT NULL,
                    zone_name       TEXT    NOT NULL,
                    dwell_seconds   REAL    NOT NULL,
                    alerted         INTEGER DEFAULT 0
                )
            """)

            # ── System logs ───────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    level     TEXT    NOT NULL,   -- INFO, WARNING, ERROR
                    source    TEXT    NOT NULL,
                    message   TEXT    NOT NULL
                )
            """)

        logger.info("Database schema ready.")

    # ── Write Methods ─────────────────────────────────────────────────────────

    def buffer_detection(self, track: dict, camera_id: str = "cam_0",
                         frame_num: int = 0):
        """
        Buffer a detection for batch write.
        Much faster than writing one row per detection per frame.
        """
        import json
        now = datetime.utcnow().isoformat()
        x1, y1, x2, y2 = track["bbox"]
        cx, cy = track["center"]

        self._batch.append((
            now,
            camera_id,
            track["track_id"],
            track["class_name"],
            track.get("class_id", 0),
            round(track["confidence"], 4),
            x1, y1, x2, y2,
            cx, cy,
            track.get("action", ""),
            json.dumps(track.get("zones", [])),
            frame_num
        ))

        if len(self._batch) >= self._batch_size:
            self.flush_detections()

    def flush_detections(self):
        """Write buffered detections to database."""
        if not self._batch:
            return
        batch = self._batch.copy()
        self._batch.clear()

        with self._cursor() as cur:
            cur.executemany("""
                INSERT INTO detections
                (timestamp, camera_id, track_id, class_name, class_id,
                 confidence, x1, y1, x2, y2, cx, cy, action, zones, frame_num)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)

    def save_alert(
        self,
        alert_type  : str,
        message     : str,
        track_id    : Optional[int]  = None,
        class_name  : Optional[str]  = None,
        zone_name   : Optional[str]  = None,
        snapshot_path: Optional[str] = None,
        clip_path   : Optional[str]  = None,
        camera_id   : str            = "cam_0"
    ) -> int:
        """Save an alert record. Returns the new row ID."""
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO alerts
                (timestamp, camera_id, alert_type, message,
                 track_id, class_name, zone_name, snapshot_path, clip_path)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (now, camera_id, alert_type, message,
                  track_id, class_name, zone_name, snapshot_path, clip_path))
            return cur.lastrowid

    def save_line_event(
        self,
        line_name  : str,
        direction  : str,
        track_id   : int,
        class_name : str,
        running_in : int,
        running_out: int,
        camera_id  : str = "cam_0"
    ):
        """Save a line crossing event."""
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO line_events
                (timestamp, camera_id, line_name, direction,
                 track_id, class_name, running_in, running_out)
                VALUES (?,?,?,?,?,?,?,?)
            """, (now, camera_id, line_name, direction,
                  track_id, class_name, running_in, running_out))

    def save_dwell_event(
        self,
        track_id     : int,
        class_name   : str,
        zone_name    : str,
        dwell_seconds: float,
        alerted      : bool = False,
        camera_id    : str  = "cam_0"
    ):
        """Save a completed dwell record when a track leaves a zone."""
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO dwell_events
                (timestamp, camera_id, track_id, class_name,
                 zone_name, dwell_seconds, alerted)
                VALUES (?,?,?,?,?,?,?)
            """, (now, camera_id, track_id, class_name,
                  zone_name, dwell_seconds, int(alerted)))

    def log(self, level: str, source: str, message: str):
        """Write a system log entry."""
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO system_logs (timestamp, level, source, message)
                VALUES (?,?,?,?)
            """, (now, level, source, message))

    def acknowledge_alert(self, alert_id: int):
        """Mark an alert as acknowledged (seen by user)."""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE alerts SET acknowledged=1 WHERE id=?",
                (alert_id,)
            )

    def close(self):
        """Flush remaining buffer and close connection cleanly."""
        self.flush_detections()
        if self._conn:
            self._conn.close()
            logger.info("Database connection closed.")
