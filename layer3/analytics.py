import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .database import Database

logger = logging.getLogger(__name__)


class Analytics:
    """
    Query engine over the SQLite database.

    Provides pre-built queries for all dashboard panels:
    - Detection counts over time
    - Class distribution
    - Hourly activity heatmap
    - Alert frequency
    - Top active zones
    - Line crossing trends
    - Dwell time statistics

    All queries return plain dicts/lists — easy to feed
    into PyQt6 charts or export to CSV/Excel.
    """

    def __init__(self, db: Database):
        self.db = db

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute a SELECT query and return list of row dicts."""
        with self.db._lock:
            cur = self.db._conn.cursor()
            try:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description] if cur.description else []
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            finally:
                cur.close()

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        """Execute a query returning a single value."""
        rows = self._query(sql, params)
        if rows:
            return list(rows[0].values())[0]
        return None

    # ── Summary Stats ─────────────────────────────────────────────────────

    def total_detections(self, hours: int = 24) -> int:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._scalar(
            "SELECT COUNT(*) FROM detections WHERE timestamp >= ?", (since,)
        ) or 0

    def total_alerts(self, hours: int = 24) -> int:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._scalar(
            "SELECT COUNT(*) FROM alerts WHERE timestamp >= ?", (since,)
        ) or 0

    def unacknowledged_alerts(self) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM alerts WHERE acknowledged=0"
        ) or 0

    def active_cameras(self) -> List[str]:
        rows = self._query(
            "SELECT DISTINCT camera_id FROM detections "
            "WHERE timestamp >= ?",
            ((datetime.utcnow() - timedelta(hours=1)).isoformat(),)
        )
        return [r["camera_id"] for r in rows]

    # ── Time-Series Data (for line charts) ────────────────────────────────

    def detections_per_hour(self, days: int = 1) -> List[Dict]:
        """
        Returns hourly detection counts for the last N days.
        Output: [{"hour": "2024-05-27 14", "count": 142}, ...]
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._query("""
            SELECT
                strftime('%Y-%m-%d %H', timestamp) AS hour,
                COUNT(*) AS count
            FROM detections
            WHERE timestamp >= ?
            GROUP BY hour
            ORDER BY hour ASC
        """, (since,))

    def alerts_per_hour(self, days: int = 1) -> List[Dict]:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._query("""
            SELECT
                strftime('%Y-%m-%d %H', timestamp) AS hour,
                COUNT(*) AS count
            FROM alerts
            WHERE timestamp >= ?
            GROUP BY hour
            ORDER BY hour ASC
        """, (since,))

    def line_crossings_over_time(
        self, line_name: str, days: int = 1
    ) -> List[Dict]:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._query("""
            SELECT
                strftime('%Y-%m-%d %H', timestamp) AS hour,
                SUM(CASE WHEN direction='in'  THEN 1 ELSE 0 END) AS entering,
                SUM(CASE WHEN direction='out' THEN 1 ELSE 0 END) AS exiting
            FROM line_events
            WHERE line_name=? AND timestamp >= ?
            GROUP BY hour
            ORDER BY hour ASC
        """, (line_name, since))

    # ── Distribution Data (for bar/pie charts) ────────────────────────────

    def detections_by_class(self, hours: int = 24) -> List[Dict]:
        """
        Returns detection count per object class.
        Output: [{"class_name": "person", "count": 843}, ...]
        """
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._query("""
            SELECT class_name, COUNT(*) AS count
            FROM detections
            WHERE timestamp >= ?
            GROUP BY class_name
            ORDER BY count DESC
        """, (since,))

    def alerts_by_type(self, hours: int = 24) -> List[Dict]:
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._query("""
            SELECT alert_type, COUNT(*) AS count
            FROM alerts
            WHERE timestamp >= ?
            GROUP BY alert_type
            ORDER BY count DESC
        """, (since,))

    def top_active_zones(self, hours: int = 24, limit: int = 5) -> List[Dict]:
        """
        Returns zones sorted by number of detection events.
        Requires zones column to be set (Layer 2 must be running).
        """
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._query("""
            SELECT zones, COUNT(*) AS detections
            FROM detections
            WHERE zones != '[]' AND zones IS NOT NULL AND timestamp >= ?
            GROUP BY zones
            ORDER BY detections DESC
            LIMIT ?
        """, (since, limit))

    # ── Dwell Time Analytics ──────────────────────────────────────────────

    def avg_dwell_per_zone(self, days: int = 7) -> List[Dict]:
        """
        Average dwell time in seconds per zone.
        Output: [{"zone_name": "Aisle 3", "avg_seconds": 42.3, "visits": 87}]
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._query("""
            SELECT
                zone_name,
                ROUND(AVG(dwell_seconds), 1) AS avg_seconds,
                COUNT(*) AS visits,
                ROUND(MAX(dwell_seconds), 1) AS max_seconds
            FROM dwell_events
            WHERE timestamp >= ?
            GROUP BY zone_name
            ORDER BY avg_seconds DESC
        """, (since,))

    # ── Recent Records (for history table in UI) ──────────────────────────

    def recent_alerts(self, limit: int = 50) -> List[Dict]:
        return self._query("""
            SELECT id, timestamp, alert_type, message,
                   track_id, class_name, zone_name,
                   snapshot_path, clip_path, acknowledged
            FROM alerts
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

    def recent_detections(self, limit: int = 100) -> List[Dict]:
        return self._query("""
            SELECT timestamp, camera_id, track_id, class_name,
                   confidence, action, zones
            FROM detections
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

    def search_alerts(
        self,
        alert_type : Optional[str] = None,
        class_name : Optional[str] = None,
        zone_name  : Optional[str] = None,
        hours      : int           = 24
    ) -> List[Dict]:
        """Flexible alert search with optional filters."""
        since   = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        clauses = ["timestamp >= ?"]
        params  = [since]

        if alert_type:
            clauses.append("alert_type = ?")
            params.append(alert_type)
        if class_name:
            clauses.append("class_name = ?")
            params.append(class_name)
        if zone_name:
            clauses.append("zone_name LIKE ?")
            params.append(f"%{zone_name}%")

        where = " AND ".join(clauses)
        return self._query(
            f"SELECT * FROM alerts WHERE {where} ORDER BY timestamp DESC LIMIT 200",
            tuple(params)
        )

    def export_to_csv(self, query_result: List[Dict], path: str):
        """Export any query result to CSV file."""
        import csv
        if not query_result:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=query_result[0].keys())
            writer.writeheader()
            writer.writerows(query_result)
        logger.info(f"Exported {len(query_result)} rows to {path}")
