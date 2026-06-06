import time
import logging
from dataclasses import dataclass, field
from typing      import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class LiveMetrics:
    """
    Snapshot of current system state — updated every frame.
    Consumed by the dashboard to display KPI cards.
    """
    fps               : float = 0.0
    object_count      : int   = 0
    person_count      : int   = 0
    vehicle_count     : int   = 0
    alerts_last_hour  : int   = 0
    alerts_today      : int   = 0
    active_zones      : int   = 0
    line_in_total     : int   = 0
    line_out_total    : int   = 0
    db_size_mb        : float = 0.0
    uptime_seconds    : float = 0.0
    frames_processed  : int   = 0
    notifications_sent: int   = 0
    redis_connected   : bool  = False


class LiveMetricsCollector:
    """
    Collects and maintains a rolling window of live metrics.

    Updates every frame from pipeline data.
    Provides smoothed values for stable UI display.
    Computes derived metrics (alerts/hour rate, peak FPS, etc.)
    """

    def __init__(self, config: dict):
        cfg               = config.get("dashboard", {})
        self._start_time  = time.time()
        self._frame_count = 0
        self._notif_count = 0

        # Rolling windows for smoothing
        self._fps_history : deque = deque(maxlen=60)
        self._obj_history : deque = deque(maxlen=30)

        # Hourly alert tracking
        self._alert_times : deque = deque(maxlen=1000)

        # Latest metrics snapshot
        self.current = LiveMetrics()

        # Analytics reference (set by DashboardManager)
        self._analytics = None

    def update(
        self,
        fps           : float,
        tracks        : list,
        line_counts   : dict,
        density_levels: dict,
        alerts_fired  : int,
        notifications : int
    ):
        """Update metrics from pipeline result. Called every frame."""
        self._frame_count += 1
        self._notif_count += notifications
        now = time.time()

        # Smooth FPS
        self._fps_history.append(fps)
        smooth_fps = sum(self._fps_history) / max(len(self._fps_history), 1)

        # Object counts by class
        persons  = sum(1 for t in tracks if t.get("class_name") == "person")
        vehicles = sum(1 for t in tracks
                       if t.get("class_name") in ("car", "truck",
                                                   "bus", "motorcycle"))

        # Track alert times for rate calculation
        for _ in range(alerts_fired):
            self._alert_times.append(now)

        # Alerts in last hour
        one_hour_ago  = now - 3600
        alerts_1h     = sum(1 for t in self._alert_times if t > one_hour_ago)

        # Line crossing totals
        total_in  = sum(c.get("in",  0) for c in line_counts.values())
        total_out = sum(c.get("out", 0) for c in line_counts.values())

        # Active zones (with at least 1 person)
        active_zones = sum(
            1 for lvl in density_levels.values()
            if lvl not in ("LOW", "_global")
        )

        # DB size
        db_size = 0.0
        if self._analytics:
            try:
                import os
                db_path = self._analytics.db.db_path
                if os.path.exists(db_path):
                    db_size = os.path.getsize(db_path) / (1024 * 1024)
            except Exception:
                pass

        self.current = LiveMetrics(
            fps               = round(smooth_fps, 1),
            object_count      = len(tracks),
            person_count      = persons,
            vehicle_count     = vehicles,
            alerts_last_hour  = alerts_1h,
            alerts_today      = self._get_alerts_today(),
            active_zones      = active_zones,
            line_in_total     = total_in,
            line_out_total    = total_out,
            db_size_mb        = round(db_size, 2),
            uptime_seconds    = round(now - self._start_time, 1),
            frames_processed  = self._frame_count,
            notifications_sent= self._notif_count,
            redis_connected   = False
        )

    def _get_alerts_today(self) -> int:
        if not self._analytics:
            return 0
        try:
            return self._analytics.total_alerts(hours=24)
        except Exception:
            return 0

    def get_uptime_str(self) -> str:
        secs = int(self.current.uptime_seconds)
        h    = secs // 3600
        m    = (secs % 3600) // 60
        s    = secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
