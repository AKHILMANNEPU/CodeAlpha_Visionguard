import cv2
import numpy as np
import time
import logging
from collections import deque

from .detector         import DetectorTracker
from .action_recognizer import ActionRecognizer
from .privacy_blur     import PrivacyBlur
from .pose_estimator   import PoseEstimator
from .visualizer       import Layer1Visualizer

from layer2.scene_manager import SceneManager
from layer3.storage_manager import StorageManager

logger = logging.getLogger(__name__)

class Layer1Pipeline:
    def __init__(self, config: dict, camera_id: str = "cam_0"):
        logger.info(f"Initializing Layer 1 Pipeline for {camera_id}...")
        self.config     = config
        self.frame_num  = 0
        
        self.detector    = DetectorTracker(config)
        self.action_rec  = ActionRecognizer(config)
        self.privacy     = PrivacyBlur(config)
        self.pose        = PoseEstimator(config)
        self.visualizer  = Layer1Visualizer(config)
        self.scene_mgr   = SceneManager(config)
        
        # Override config's camera_id for this pipeline's storage manager
        pipeline_config = config.copy()
        if "camera" not in pipeline_config:
            pipeline_config["camera"] = {}
        pipeline_config["camera"]["id"] = camera_id
        
        self.storage_mgr = StorageManager(pipeline_config)
        
        self._fps_times  = deque(maxlen=30)
        logger.info("Layer 1 Pipeline ready.")

    def process(self, frame: np.ndarray, camera_id: str = "cam_0") -> dict:
        t_start = time.perf_counter()
        self.frame_num += 1

        tracks = self.detector.process(frame)

        if not hasattr(self, "last_pose_data"):
            self.last_pose_data = {}

        if self.frame_num % 2 == 0:
            self.last_pose_data = self.pose.process(frame)
            
        pose_data = self.last_pose_data

        tracks = self.action_rec.update(tracks, pose_data)

        display_frame = self.privacy.process(frame.copy())
        annotated = self.visualizer.draw(display_frame, tracks, pose_data)

        # Pass through Layer 2
        l2_result = self.scene_mgr.process(tracks, annotated)
        annotated = l2_result["annotated_frame"]

        self._fps_times.append(time.perf_counter())
        fps = 0.0
        if len(self._fps_times) > 1:
            elapsed = self._fps_times[-1] - self._fps_times[0]
            fps = (len(self._fps_times) - 1) / max(elapsed, 1e-6)

        # Pass through Layer 3 (Storage)
        l3_result = self.storage_mgr.process(l2_result, frame.copy(), fps)

        return {
            "annotated_frame" : annotated,
            "tracks"          : tracks,
            "pose_data"       : pose_data,
            "fps"             : fps,
            "frame_num"       : self.frame_num,
            "alerts"          : l2_result["alerts"],
            "saved_alerts"    : l3_result["saved_alerts"],
            "line_counts"     : l2_result["line_counts"],
            "density_levels"  : l2_result["density_levels"]
        }

    def toggle_blur(self, enabled: bool):
        self.privacy.toggle(enabled)

    def toggle_pose(self, enabled: bool):
        self.pose.enabled = enabled
        if enabled and self.pose.model is None:
            self.pose = PoseEstimator(self.config)

    def set_confidence(self, value: float):
        self.detector.conf = value

    def close(self):
        self.storage_mgr.close()
