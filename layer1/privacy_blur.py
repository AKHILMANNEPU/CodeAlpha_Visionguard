import cv2
import numpy as np
import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class PrivacyBlur:
    def __init__(self, config: dict):
        cfg = config.get("privacy", {})
        self.blur_faces    = cfg.get("blur_faces", True)
        self.blur_plates   = cfg.get("blur_plates", True)
        self.blur_mode     = cfg.get("blur_mode", "gaussian")
        self.blur_strength = cfg.get("blur_strength", 51)
        self.model_path    = cfg.get("face_model", "yolov8n-face.pt")
        self.enabled       = cfg.get("enabled", False)

        self.mp_face_detection = None
        self.face_detector = None

        if self.enabled:
            self._load_models()

    def _load_models(self):
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            
            import os
            model_path = 'models/blaze_face_short_range.tflite'
            if not os.path.exists(model_path):
                import urllib.request
                logger.info("Downloading MediaPipe face model...")
                urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite', model_path)
            
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.4)
            self.face_detector = vision.FaceDetector.create_from_options(options)
            
            self.mp_image = mp.Image
            self.mp_image_format = mp.ImageFormat
            logger.info("MediaPipe Tasks Face Detection loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load MediaPipe: {e}")

        if self.blur_plates:
            try:
                plate_path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
                self.plate_cascade = cv2.CascadeClassifier(plate_path)
            except Exception:
                self.plate_cascade = None
                logger.warning("License plate cascade not found. Plate blur disabled.")

    def toggle(self, enabled: bool):
        self.enabled = enabled
        if enabled and self.face_detector is None:
            self._load_models()
        logger.info(f"Privacy blur {'enabled' if enabled else 'disabled'}.")

    def process(self, frame: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return frame

        result = frame.copy()

        if self.blur_faces:
            result = self._blur_faces(result)

        if self.blur_plates and hasattr(self, "plate_cascade") and self.plate_cascade:
            result = self._blur_plates(result)

        return result

    def _blur_faces(self, frame: np.ndarray) -> np.ndarray:
        if getattr(self, "face_detector", None) is None:
            return frame
            
        regions = []
        # MediaPipe requires RGB images
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self.mp_image(image_format=self.mp_image_format.SRGB, data=rgb_frame)
        
        results = self.face_detector.detect(mp_image)
        
        if results.detections:
            for detection in results.detections:
                bbox = detection.bounding_box
                x1 = int(bbox.origin_x)
                y1 = int(bbox.origin_y)
                x2 = int(bbox.origin_x + bbox.width)
                y2 = int(bbox.origin_y + bbox.height)
                regions.append((x1, y1, x2, y2))

        for (x1, y1, x2, y2) in regions:
            # Add a slight padding to the bounding box to cover the whole face
            pad_w = int((x2 - x1) * 0.1)
            pad_h = int((y2 - y1) * 0.1)
            x1, y1 = max(0, x1 - pad_w), max(0, y1 - pad_h)
            x2, y2 = min(frame.shape[1], x2 + pad_w), min(frame.shape[0], y2 + pad_h)
            if x2 > x1 and y2 > y1:
                frame[y1:y2, x1:x2] = self._apply_blur(frame[y1:y2, x1:x2])
        return frame

    def _blur_plates(self, frame: np.ndarray) -> np.ndarray:
        gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        plates = self.plate_cascade.detectMultiScale(gray, 1.1, 5)
        for (x, y, w, h) in plates:
            x2, y2 = x + w, y + h
            frame[y:y2, x:x2] = self._apply_blur(frame[y:y2, x:x2])
        return frame

    def _apply_blur(self, region: np.ndarray) -> np.ndarray:
        if region.size == 0:
            return region

        if self.blur_mode == "pixelate":
            h, w   = region.shape[:2]
            block  = max(1, self.blur_strength // 10)
            small  = cv2.resize(region, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_LINEAR)
            return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            k = self.blur_strength if self.blur_strength % 2 == 1 else self.blur_strength + 1
            return cv2.GaussianBlur(region, (k, k), 0)
