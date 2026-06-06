import numpy as np
import logging
import torch

# Fix PyTorch 2.6 unpickling error for YOLOv8
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from ultralytics import YOLO

logger = logging.getLogger(__name__)

# All 80 COCO class names
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush"
]


class DetectorTracker:
    """
    YOLOv8 detection + ByteTrack tracking.
    ByteTrack is built into ultralytics — no separate install.
    """

    def __init__(self, config: dict):
        cfg = config["detection"]
        self.model_path   = cfg.get("model_path", "yolov8n.pt")
        self.conf         = cfg.get("confidence_threshold", 0.5)
        self.iou          = cfg.get("iou_threshold", 0.45)
        self.device       = cfg.get("device", "cpu") # Changed to CPU explicitly to prevent torch errors on this machine
        self.classes      = cfg.get("classes", None)
        self.tracker_cfg  = cfg.get("tracker", "bytetrack.yaml")

        logger.info(f"Loading detector: {self.model_path} on {self.device}")
        self.model = YOLO(self.model_path)
        logger.info("Detector loaded. ByteTrack tracker ready.")

    def process(self, frame: np.ndarray) -> list:
        """
        Run YOLOv8 + ByteTrack on one frame.

        Returns list of dicts, one per tracked object.
        """
        results = self.model.track(
            source=frame,
            conf=self.conf,
            iou=self.iou,
            classes=self.classes,
            tracker=self.tracker_cfg,
            device=self.device,
            persist=True,
            verbose=False
        )[0]

        tracks = []

        if results.boxes is None or results.boxes.id is None:
            return tracks

        for box in results.boxes:
            if box.id is None:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            track_id        = int(box.id[0])
            class_id        = int(box.cls[0])
            confidence      = float(box.conf[0])
            cx              = (x1 + x2) // 2
            cy              = (y1 + y2) // 2

            tracks.append({
                "track_id"   : track_id,
                "class_id"   : class_id,
                "class_name" : self.get_class_name(class_id),
                "confidence" : confidence,
                "bbox"       : [x1, y1, x2, y2],
                "center"     : (cx, cy)
            })

        return tracks

    @staticmethod
    def get_class_name(class_id: int) -> str:
        if 0 <= class_id < len(COCO_CLASSES):
            return COCO_CLASSES[class_id]
        return f"class_{class_id}"
