import cv2
import numpy as np
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore    import QThread, pyqtSignal, Qt
from PyQt6.QtGui     import QImage, QPixmap


from layer6.ingestion import CameraStream

class PipelineThread(QThread):
    frame_ready = pyqtSignal(np.ndarray, str) # Added camera_id to signal
    stats_ready = pyqtSignal(float, int, str)
    alert_ready = pyqtSignal(str)
    saved_alerts_ready = pyqtSignal(list, list)
    layer5_metrics_ready = pyqtSignal(dict)

    def __init__(self, pipeline, video_source, camera_id="cam_0", parent=None):
        super().__init__(parent)
        self.pipeline     = pipeline
        self.video_source = video_source
        self.camera_id    = camera_id
        self.running      = False

    def run(self):
        try:
            self.running = True
            stream = CameraStream(self.video_source)

            while self.running:
                ret, frame = stream.read()
                if not ret:
                    break

                result = self.pipeline.process(frame, self.camera_id)

                self.frame_ready.emit(result["annotated_frame"], self.camera_id)
                self.stats_ready.emit(result["fps"], len(result["tracks"]), self.camera_id)

                for track in result["tracks"]:
                    action = track.get("action", "")
                    if "⚠" in action:
                        self.alert_ready.emit(f"ALERT: {action} — Track #{track['track_id']} ({track['class_name']})")
                        
                for alert in result.get("alerts", []):
                    self.alert_ready.emit(alert)
                    
                saved_alerts = result.get("saved_alerts", [])
                raw_alerts = result.get("alerts", [])
                if saved_alerts:
                    self.saved_alerts_ready.emit(saved_alerts, raw_alerts)
                    
                metrics_dict = {
                    "fps": result["fps"],
                    "tracks": result["tracks"],
                    "line_counts": result.get("line_counts", {}),
                    "density_levels": result.get("density_levels", {}),
                    "alerts_fired": len(saved_alerts),
                    "notifications": len(saved_alerts) # Approximation
                }
                self.layer5_metrics_ready.emit(metrics_dict)
                        
                # Yield to GUI thread
                self.msleep(10)

            stream.release()
            self.running = False
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.alert_ready.emit(f"CRITICAL ERROR: {str(e)}")
            self.running = False

    def stop(self):
        self.running = False
        self.wait()


class VideoWidget(QWidget):
    click_event = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("No Signal")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: #0a0a0a; color: #444; font-size: 14px;")
        self.label.mousePressEvent = self._on_label_click

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        
        self.last_w = 1280
        self.last_h = 720

    def _on_label_click(self, event):
        lbl_w = self.label.width()
        lbl_h = self.label.height()
        
        # Simple scaling mapping (assuming video fills most of the label)
        scale_w = self.last_w / max(lbl_w, 1)
        scale_h = self.last_h / max(lbl_h, 1)
        scale = max(scale_w, scale_h) # KeepAspectRatio usually aligns to one axis
        
        # Rough estimation
        x = int(event.position().x() * scale_w)
        y = int(event.position().y() * scale_h)
        self.click_event.emit(x, y)

    def update_frame(self, frame: np.ndarray):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch  = rgb_frame.shape
        self.last_h, self.last_w = h, w
        bytes_per_line = ch * w

        q_image  = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        pixmap   = QPixmap.fromImage(q_image)

        pixmap = pixmap.scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(pixmap)
