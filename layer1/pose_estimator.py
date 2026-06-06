import numpy as np
import cv2
import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"
]

SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)
]

PART_COLORS = {
    "head"   : (255, 200, 0),
    "arms"   : (0, 200, 255),
    "torso"  : (0, 255, 100),
    "legs"   : (255, 100, 200)
}

SKELETON_COLORS = [
    PART_COLORS["head"], PART_COLORS["head"], PART_COLORS["head"], PART_COLORS["head"],
    PART_COLORS["torso"], PART_COLORS["arms"], PART_COLORS["arms"], PART_COLORS["arms"], PART_COLORS["arms"],
    PART_COLORS["torso"], PART_COLORS["torso"], PART_COLORS["torso"],
    PART_COLORS["legs"], PART_COLORS["legs"], PART_COLORS["legs"], PART_COLORS["legs"]
]

class PoseEstimator:
    def __init__(self, config: dict):
        cfg = config.get("pose", {})
        self.enabled      = cfg.get("enabled", True)
        self.model_path   = cfg.get("model_path", "yolov8n-pose.pt")
        self.conf         = cfg.get("confidence", 0.5)
        self.device       = config["detection"].get("device", "cpu")
        self.draw_skeleton= cfg.get("draw_skeleton", True)
        self.kp_radius    = cfg.get("keypoint_radius", 4)
        self.kp_threshold = cfg.get("keypoint_conf_threshold", 0.5)

        self.model = None
        if self.enabled:
            logger.info(f"Loading pose model: {self.model_path}")
            self.model = YOLO(self.model_path)
            logger.info("Pose model loaded.")

    def process(self, frame: np.ndarray) -> dict:
        if not self.enabled or self.model is None:
            return {}

        results = self.model.predict(
            frame,
            conf=self.conf,
            device=self.device,
            verbose=False
        )[0]

        pose_data = {}

        if results.keypoints is None:
            return pose_data

        for i, (kps, box) in enumerate(zip(results.keypoints, results.boxes)):
            keypoints = kps.data[0].cpu().numpy()
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            pose_data[i] = {
                "keypoints": [(float(x), float(y), float(c)) for x, y, c in keypoints],
                "bbox"     : [x1, y1, x2, y2]
            }

        return pose_data
