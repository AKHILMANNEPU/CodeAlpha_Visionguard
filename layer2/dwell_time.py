import time
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DwellRecord:
    """Tracks how long a single track has been in a single zone."""
    track_id    : int
    zone_name   : str
    class_name  : str
    entered_at  : float = field(default_factory=time.time)
    last_seen   : float = field(default_factory=time.time)

    @property
    def duration_seconds(self) -> float:
        return self.last_seen - self.entered_at

    @property
    def duration_str(self) -> str:
        secs = int(self.duration_seconds)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"


class DwellTimeAnalyzer:
    """
    Tracks how long each object spends inside each zone.

    Applications:
    - Retail: Which shelf/section holds customer attention longest?
    - Security: Is someone loitering in a restricted area?
    - Healthcare: How long is a patient in a waiting zone?
    - Manufacturing: Is a worker spending too long in a danger zone?

    Works alongside ZoneIntrusionDetector — uses the "zones" key
    added to each track dict by ZoneIntrusionDetector.update().
    """

    def __init__(self, config: dict):
        cfg = config.get("dwell", {})
        self.alert_threshold_sec = cfg.get("alert_threshold_seconds", 30)
        self.alert_cooldown_sec  = cfg.get("alert_cooldown_seconds",   60)
        self.track_classes       = cfg.get("track_classes", ["person"])

        # Active dwell records: { (track_id, zone_name): DwellRecord }
        self._records: Dict[Tuple[int,str], DwellRecord] = {}

        # Alert cooldown: { (track_id, zone_name): last_alert_time }
        self._last_alert: Dict[Tuple[int,str], float] = {}

        # Historical dwell data (for analytics)
        # { zone_name: [duration_seconds, ...] }
        self._history: Dict[str, List[float]] = {}

    def update(self, tracks: list) -> Tuple[list, List[str]]:
        """
        Update dwell times for all tracks.

        Requires tracks to already have "zones" key set by
        ZoneIntrusionDetector.update().

        Returns:
            (tracks_with_dwell, dwell_alerts)
            tracks_with_dwell: tracks with "dwell_times" key added
            dwell_alerts     : alerts for tracks exceeding threshold
        """
        alerts     = []
        now        = time.time()
        active_keys= set()

        for track in tracks:
            tid      = track["track_id"]
            cls_name = track["class_name"]
            zones    = track.get("zones", [])

            # Only track configured classes
            if cls_name not in self.track_classes and "all" not in self.track_classes:
                track["dwell_times"] = {}
                continue

            dwell_times = {}

            for zone_name in zones:
                key = (tid, zone_name)
                active_keys.add(key)

                if key not in self._records:
                    # New entry into zone
                    self._records[key] = DwellRecord(
                        track_id   = tid,
                        zone_name  = zone_name,
                        class_name = cls_name
                    )
                else:
                    # Update last seen
                    self._records[key].last_seen = now

                record   = self._records[key]
                duration = record.duration_seconds
                dwell_times[zone_name] = {
                    "seconds"   : duration,
                    "label"     : record.duration_str
                }

                # Alert check
                if duration >= self.alert_threshold_sec:
                    last_t = self._last_alert.get(key, 0)
                    if now - last_t > self.alert_cooldown_sec:
                        alert = (f"⏱ DWELL ALERT | {cls_name.upper()} #{tid} "
                                 f"in '{zone_name}' for {record.duration_str}")
                        alerts.append(alert)
                        self._last_alert[key] = now
                        logger.warning(alert)

            track["dwell_times"] = dwell_times

        # Clean up completed dwell records (track left zone)
        for key in list(self._records.keys()):
            if key not in active_keys:
                record = self._records[key]
                # Save to history for analytics
                if record.zone_name not in self._history:
                    self._history[record.zone_name] = []
                self._history[record.zone_name].append(record.duration_seconds)
                del self._records[key]

        return tracks, alerts

    def get_zone_avg_dwell(self, zone_name: str) -> Optional[float]:
        """Average dwell time in seconds for a zone (from history)."""
        history = self._history.get(zone_name, [])
        if not history:
            return None
        return sum(history) / len(history)

    def get_all_active(self) -> List[DwellRecord]:
        """All currently active dwell records — for dashboard display."""
        return list(self._records.values())

    def get_zone_stats(self) -> Dict[str, dict]:
        """Summary stats per zone for analytics panel."""
        stats = {}
        for zone_name, durations in self._history.items():
            if durations:
                import numpy as np
                stats[zone_name] = {
                    "count"  : len(durations),
                    "avg_sec": float(np.mean(durations)),
                    "max_sec": float(np.max(durations)),
                    "min_sec": float(np.min(durations))
                }
        return stats
