import numpy as np
import logging
from typing import Dict, Any, List

from .database       import Database
from .redis_cache    import RedisCache
from .clip_storage   import ClipStorage
from .event_log      import EventLog
from .analytics      import Analytics

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Master controller for Layer 3 (Data & Storage Pipeline).
    Integrates Database, Redis, Video Clips, Event Logging, and Analytics.
    """

    def __init__(self, config: dict):
        logger.info("Initializing Layer 3 Storage Manager...")

        self.config = config

        self.db           = Database(config)
        self.redis        = RedisCache(config)
        self.clip_storage = ClipStorage(config)
        self.event_log    = EventLog(self.db, self.clip_storage, config)
        self.analytics    = Analytics(self.db)
        
        # Link redis to event_log if available
        self.event_log._redis = self.redis

        self.camera_id = config.get("camera", {}).get("id", "cam_0")
        self.frame_count = 0

        logger.info("Layer 3 Storage Manager ready.")

    def process(self, layer2_result: dict, raw_frame: np.ndarray, fps: float = 0.0) -> dict:
        """
        Process the output from Layer 2.

        Args:
            layer2_result: The result dict from SceneManager.process()
            raw_frame: Original BGR frame from camera (without annotations, for clip storage)
            fps: Current processing FPS
        
        Returns:
            StorageResult dictionary with metrics about what was saved.
        """
        self.frame_count += 1
        
        tracks         = layer2_result.get("tracks", [])
        alerts         = layer2_result.get("alerts", [])
        annotated      = layer2_result.get("annotated_frame", raw_frame)
        line_counts    = layer2_result.get("line_counts", {})
        density_levels = layer2_result.get("density_levels", {})

        # 1. Update Video Clip Storage (ring buffer)
        self.clip_storage.update(raw_frame)

        # 2. Buffer detections to database (only every Nth frame to save space/I/O if desired, 
        # but for now we buffer all and it flushes automatically)
        for track in tracks:
            self.db.buffer_detection(track, self.camera_id, self.frame_count)

        # 3. Process Alerts
        saved_alerts = []
        if alerts:
            # We pass the annotated frame so the snapshot has boxes/zones drawn
            saved_alerts = self.event_log.process_alerts(alerts, annotated, self.camera_id)

        # 4. Update Redis Real-Time State
        if self.redis:
            self.redis.update_live_tracks(tracks)
            self.redis.update_fps(fps)
            self.redis.update_line_counts(line_counts)
            self.redis.update_density(density_levels)

        # 5. Extract Dwell and Line Events (simplified saving logic)
        # Note: Line crossing and dwell time alerts are already string alerts captured above.
        # But we can also save structured line_events and dwell_events if needed here.
        # (Assuming Layer 2 handles emitting the alert strings that EventLog parses)
        
        return {
            "saved_detections": len(tracks),
            "saved_alerts": saved_alerts,
            "db_status": "ok"
        }

    def close(self):
        """Shutdown Layer 3 storage cleanly."""
        logger.info("Closing StorageManager...")
        self.db.close()
