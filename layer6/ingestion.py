import cv2
import time
import logging

logger = logging.getLogger(__name__)

class CameraStream:
    """
    Robust camera stream reader with auto-reconnect logic.
    Handles Webcams, RTSP streams, and Video Files.
    """
    def __init__(self, source):
        # Convert string "0" to int 0 for webcam
        if isinstance(source, str) and source.isdigit():
            self.source = int(source)
        else:
            self.source = source
            
        self.cap = None
        self._connect()

    def _connect(self):
        """Attempt to connect to the video source."""
        if self.cap is not None:
            self.cap.release()
            
        logger.info(f"Connecting to video source: {self.source}")
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"Failed to open video source: {self.source}")
            return False
        return True

    def read(self):
        """Read a frame, automatically reconnecting if stream drops."""
        if self.cap is None or not self.cap.isOpened():
            # Try to reconnect
            logger.warning(f"Stream lost. Attempting to reconnect to {self.source}...")
            time.sleep(2) # Cooldown before reconnect
            if not self._connect():
                return False, None

        ret, frame = self.cap.read()
        if not ret:
            # For video files, EOF means we should stop, not reconnect.
            # But for RTSP/Webcams, we should try to reconnect.
            # We assume string sources that are not digit and not rtsp/http are local files.
            if isinstance(self.source, str) and not (self.source.startswith("rtsp://") or self.source.startswith("http://")):
                return False, None
                
            logger.warning(f"Frame dropped. Attempting to reconnect to {self.source}...")
            time.sleep(2)
            if self._connect():
                ret, frame = self.cap.read()
            
        return ret, frame

    def release(self):
        """Release the capture device."""
        if self.cap:
            self.cap.release()
            self.cap = None
