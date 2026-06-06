import numpy as np
import time
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DensityLevel:
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    CRITICAL = "CRITICAL"


class CrowdDensityEstimator:
    """
    Estimates crowd density per zone.

    Two measurement approaches:
    1. Count-based: raw number of people in a zone
    2. Area-based: people per m² (requires camera calibration)

    For simplicity and zero-calibration, we use count-based
    with configurable thresholds. This is what most commercial
    systems use without dedicated depth sensors.

    Alert hierarchy:
        LOW      : 0   to low_thresh  people → no alert
        MEDIUM   : low to med_thresh  people → yellow alert
        HIGH     : med to high_thresh people → orange alert
        CRITICAL : above high_thresh  people → red alert, notify immediately
    """

    def __init__(self, config: dict):
        cfg = config.get("crowd", {})
        self.low_thresh    = cfg.get("low_threshold",      3)
        self.med_thresh    = cfg.get("medium_threshold",   8)
        self.high_thresh   = cfg.get("high_threshold",    15)
        self.alert_levels  = cfg.get("alert_on",          ["HIGH", "CRITICAL"])
        self.cooldown_sec  = cfg.get("cooldown_seconds",  30)

        # Per-zone history for smoothing (avoid flapping)
        self._zone_counts   : Dict[str, List[int]]   = {}
        self._smoothing_len : int                    = cfg.get("smoothing_frames", 10)
        self._last_alert    : Dict[str, float]       = {}

        # Global crowd count (entire frame)
        self._global_history: List[int] = []

    def update(
        self,
        tracks      : list,
        zone_occupancy : Dict[str, int]   # from ZoneIntrusionDetector
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Compute density levels and generate alerts.

        Args:
            tracks        : All active tracks (for global count)
            zone_occupancy: {zone_name: count} from ZoneIntrusionDetector

        Returns:
            (density_levels, alerts)
            density_levels : { zone_name: "LOW"/"MEDIUM"/"HIGH"/"CRITICAL" }
            alerts         : list of alert strings
        """
        alerts        = {}
        density_levels= {}
        now           = time.time()

        # Global density (whole frame)
        global_count = len([t for t in tracks if t["class_name"] == "person"])
        self._global_history.append(global_count)
        if len(self._global_history) > self._smoothing_len:
            self._global_history.pop(0)
        smoothed_global = int(np.mean(self._global_history))
        density_levels["_global"] = self._classify(smoothed_global)

        # Per-zone density
        for zone_name, count in zone_occupancy.items():
            if zone_name not in self._zone_counts:
                self._zone_counts[zone_name] = []

            self._zone_counts[zone_name].append(count)
            if len(self._zone_counts[zone_name]) > self._smoothing_len:
                self._zone_counts[zone_name].pop(0)

            smoothed = int(np.mean(self._zone_counts[zone_name]))
            level    = self._classify(smoothed)
            density_levels[zone_name] = level

            # Alert check
            if level in self.alert_levels:
                last_t = self._last_alert.get(zone_name, 0)
                if now - last_t > self.cooldown_sec:
                    alert = (f"👥 CROWD {level} | Zone '{zone_name}' "
                             f"has {smoothed} people — level: {level}")
                    alerts[zone_name] = alert
                    self._last_alert[zone_name] = now
                    logger.warning(alert)

        return density_levels, list(alerts.values())

    def _classify(self, count: int) -> str:
        if count >= self.high_thresh:  return DensityLevel.CRITICAL
        if count >= self.med_thresh:   return DensityLevel.HIGH
        if count >= self.low_thresh:   return DensityLevel.MEDIUM
        return DensityLevel.LOW

    def get_global_level(self) -> str:
        if not self._global_history:
            return DensityLevel.LOW
        return self._classify(int(np.mean(self._global_history)))

    def get_density_color(self, level: str):
        """BGR color for density level — used by visualizer."""
        return {
            DensityLevel.LOW     : (0, 255, 0),       # green
            DensityLevel.MEDIUM  : (0, 255, 255),     # yellow
            DensityLevel.HIGH    : (0, 165, 255),     # orange
            DensityLevel.CRITICAL: (0, 0, 255),       # red
        }.get(level, (200, 200, 200))
