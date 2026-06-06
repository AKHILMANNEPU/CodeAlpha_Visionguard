import logging
import re
from typing import Optional
from .database    import Database
from .clip_storage import ClipStorage

logger = logging.getLogger(__name__)


# Alert type classification from alert message strings
ALERT_TYPE_PATTERNS = {
    "ZONE_ENTRY"   : r"ZONE ENTRY",
    "ZONE_EXIT"    : r"ZONE EXIT",
    "LINE_CROSS"   : r"LINE CROSS",
    "CROWD_HIGH"   : r"CROWD HIGH|CROWD CRITICAL",
    "DWELL"        : r"DWELL ALERT",
    "FALLING"      : r"Falling",
    "LOITERING"    : r"Loitering",
}


class EventLog:
    """
    Receives alert strings from Layer 2 and persists them.

    Responsibilities:
    1. Parse alert strings → structured data (type, track_id, zone_name)
    2. Trigger clip recording for important alert types
    3. Save snapshot of the alert frame
    4. Write structured record to SQLite
    5. Write to Redis cache for live dashboard

    The alert pipeline:
        Layer 2 emits: "🔴 ZONE ENTRY | PERSON #3 entered 'Restricted Area A'"
        EventLog:
            → parses type=ZONE_ENTRY, track_id=3, zone=Restricted Area A
            → saves snapshot JPEG
            → triggers ClipStorage.save_clip()
            → writes to DB: alerts table
            → pushes to Redis: last_alert key
    """

    def __init__(self, db: Database, clip_storage: ClipStorage,
                 config: dict):
        self.db           = db
        self.clips        = clip_storage
        cfg               = config.get("storage", {})
        self.clip_on_types= cfg.get("clip_on_alert_types",
                                    ["ZONE_ENTRY", "DWELL", "CROWD_HIGH"])
        self.snap_on_types= cfg.get("snapshot_on_alert_types",
                                    ["ZONE_ENTRY", "ZONE_EXIT",
                                     "FALLING", "LOITERING"])
        self._redis       = None   # set by StorageManager after init

    def process_alerts(
        self,
        alerts    : list,
        frame     : "np.ndarray",
        camera_id : str = "cam_0"
    ) -> list:
        """
        Process a list of alert strings from Layer 2.

        Args:
            alerts   : list of alert message strings
            frame    : current annotated frame (for snapshot)
            camera_id: source camera identifier

        Returns:
            List of saved alert records with clip/snapshot paths.
        """
        saved = []

        for message in alerts:
            alert_type   = self._classify(message)
            track_id     = self._extract_track_id(message)
            zone_name    = self._extract_zone(message)
            class_name   = self._extract_class(message)

            snapshot_path = ""
            clip_path     = ""

            # Save snapshot
            if alert_type in self.snap_on_types:
                snapshot_path = self.clips.save_snapshot(
                    frame, alert_type, camera_id
                )

            # Start clip recording
            if alert_type in self.clip_on_types:
                clip_path = self.clips.save_clip(alert_type, camera_id)

            # Write to database
            alert_id = self.db.save_alert(
                alert_type    = alert_type,
                message       = message,
                track_id      = track_id,
                class_name    = class_name,
                zone_name     = zone_name,
                snapshot_path = snapshot_path,
                clip_path     = clip_path,
                camera_id     = camera_id
            )

            # Push to Redis
            if self._redis:
                self._redis.push_alert(message)

            record = {
                "id"           : alert_id,
                "type"         : alert_type,
                "message"      : message,
                "track_id"     : track_id,
                "zone_name"    : zone_name,
                "snapshot_path": snapshot_path,
                "clip_path"    : clip_path
            }
            saved.append(record)
            logger.info(f"Alert logged [{alert_type}]: {message[:80]}")

        return saved

    def _classify(self, message: str) -> str:
        for alert_type, pattern in ALERT_TYPE_PATTERNS.items():
            if re.search(pattern, message, re.IGNORECASE):
                return alert_type
        return "GENERAL"

    def _extract_track_id(self, message: str) -> Optional[int]:
        match = re.search(r"#(\d+)", message)
        return int(match.group(1)) if match else None

    def _extract_zone(self, message: str) -> Optional[str]:
        match = re.search(r"'([^']+)'", message)
        return match.group(1) if match else None

    def _extract_class(self, message: str) -> Optional[str]:
        for cls in ["PERSON", "CAR", "TRUCK", "BICYCLE", "MOTORCYCLE"]:
            if cls in message.upper():
                return cls.lower()
        return None
