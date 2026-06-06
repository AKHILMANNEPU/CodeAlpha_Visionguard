import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class Zone:
    """
    A single named polygon zone.

    Points stored as a list of (x, y) pixel coordinates.
    User draws these by clicking on the video frame in the UI.

    Example:
        Zone(
            name="Restricted Area A",
            points=[(100,100),(300,100),(300,400),(100,400)],
            color=(0,0,255),
            alert_classes=["person"],
            alert_on_entry=True
        )
    """
    name          : str
    points        : List[Tuple[int,int]]
    color         : Tuple[int,int,int] = (0, 0, 255)       # BGR red default
    alert_classes : List[str]          = field(default_factory=lambda: ["person"])
    alert_on_entry: bool               = True
    alert_on_exit : bool               = False
    max_capacity  : Optional[int]      = None               # crowd limit


class ZoneIntrusionDetector:
    """
    Detects when tracked objects enter or exit user-defined polygon zones.

    How it works:
        cv2.pointPolygonTest(polygon, point, measureDist=False)
        Returns >= 0 if point is INSIDE or ON the polygon.
        Returns < 0  if point is OUTSIDE.

    Uses track CENTER POINT (bottom-center of bbox for people,
    actual center for vehicles) for more accurate ground position.
    """

    def __init__(self, config: dict):
        cfg = config.get("zones", {})
        self.alert_cooldown = cfg.get("alert_cooldown_seconds", 5)

        # Active zones — added by user drawing in UI
        self.zones: List[Zone] = []

        # Track state: which zones each track is currently inside
        # { track_id: set(zone_names) }
        self._track_zone_state: Dict[int, set] = {}

        # Alert cooldown: prevent alert spam
        # { (track_id, zone_name): last_alert_timestamp }
        self._last_alert_time: Dict[tuple, float] = {}

        # Load zones from config if provided
        self._load_zones_from_config(cfg)

    def _load_zones_from_config(self, cfg: dict):
        """Load any predefined zones from config.yaml."""
        for z in cfg.get("predefined_zones", []):
            self.add_zone(Zone(
                name          = z["name"],
                points        = [tuple(p) for p in z["points"]],
                color         = tuple(z.get("color", [0, 0, 255])),
                alert_classes = z.get("alert_classes", ["person"]),
                alert_on_entry= z.get("alert_on_entry", True),
                alert_on_exit = z.get("alert_on_exit", False),
                max_capacity  = z.get("max_capacity", None)
            ))

    def add_zone(self, zone: Zone):
        """Add a zone. Called when user finishes drawing a polygon in UI."""
        self.zones.append(zone)
        logger.info(f"Zone added: '{zone.name}' with {len(zone.points)} vertices")

    def remove_zone(self, name: str):
        """Remove zone by name."""
        self.zones = [z for z in self.zones if z.name != name]
        logger.info(f"Zone removed: '{name}'")

    def clear_zones(self):
        self.zones.clear()
        self._track_zone_state.clear()

    def update(self, tracks: list) -> Tuple[list, List[str]]:
        """
        Check all tracks against all zones.

        Args:
            tracks: List of track dicts from Layer 1

        Returns:
            (enriched_tracks, alerts)
            enriched_tracks : same list with "zones" key added per track
            alerts          : list of alert strings fired this frame
        """
        alerts     = []
        now        = time.time()
        active_ids = set()

        for track in tracks:
            tid       = track["track_id"]
            cls_name  = track["class_name"]
            x1,y1,x2,y2 = track["bbox"]
            active_ids.add(tid)

            # Use bottom-center for people (ground position),
            # center for vehicles and objects
            if cls_name == "person":
                check_point = ((x1 + x2) // 2, y2)        # feet position
            else:
                check_point = ((x1 + x2) // 2, (y1 + y2) // 2)

            # Current zones this track is inside
            current_zones = set()

            for zone in self.zones:
                if len(zone.points) < 3:
                    continue

                polygon = np.array(zone.points, dtype=np.int32)
                inside  = cv2.pointPolygonTest(
                    polygon, (float(check_point[0]), float(check_point[1])), False
                ) >= 0

                if inside:
                    current_zones.add(zone.name)

            # Compare to previous state to detect entry/exit events
            prev_zones = self._track_zone_state.get(tid, set())

            # Entry events
            entered_zones = current_zones - prev_zones
            for zone_name in entered_zones:
                zone = self._get_zone(zone_name)
                if zone and zone.alert_on_entry:
                    if cls_name in zone.alert_classes or "all" in zone.alert_classes:
                        cooldown_key = (tid, zone_name, "entry")
                        last_t = self._last_alert_time.get(cooldown_key, 0)
                        if now - last_t > self.alert_cooldown:
                            alert = (f"🔴 ZONE ENTRY | {cls_name.upper()} #{tid} "
                                     f"entered '{zone_name}'")
                            alerts.append(alert)
                            self._last_alert_time[cooldown_key] = now
                            logger.warning(alert)

            # Exit events
            exited_zones = prev_zones - current_zones
            for zone_name in exited_zones:
                zone = self._get_zone(zone_name)
                if zone and zone.alert_on_exit:
                    if cls_name in zone.alert_classes or "all" in zone.alert_classes:
                        cooldown_key = (tid, zone_name, "exit")
                        last_t = self._last_alert_time.get(cooldown_key, 0)
                        if now - last_t > self.alert_cooldown:
                            alert = (f"🟡 ZONE EXIT | {cls_name.upper()} #{tid} "
                                     f"left '{zone_name}'")
                            alerts.append(alert)
                            self._last_alert_time[cooldown_key] = now

            # Update state
            self._track_zone_state[tid] = current_zones

            # Add zone info to track dict for downstream use
            track["zones"] = list(current_zones)

        # Clean up disappeared tracks
        for tid in list(self._track_zone_state.keys()):
            if tid not in active_ids:
                del self._track_zone_state[tid]

        return tracks, alerts

    def _get_zone(self, name: str) -> Optional[Zone]:
        for z in self.zones:
            if z.name == name:
                return z
        return None

    def get_zone_occupancy(self) -> Dict[str, int]:
        """Return current number of tracks inside each zone."""
        occupancy = {z.name: 0 for z in self.zones}
        for zone_set in self._track_zone_state.values():
            for zone_name in zone_set:
                if zone_name in occupancy:
                    occupancy[zone_name] += 1
        return occupancy
