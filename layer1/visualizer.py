import cv2
import numpy as np
import colorsys
from typing import List

def _make_colors(n: int = 100):
    colors = []
    for i in range(n):
        h = i / n
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.95)
        colors.append((int(b * 255), int(g * 255), int(r * 255)))
    return colors

_COLORS = _make_colors(100)

ACTION_COLORS = {
    "Running"      : (0, 165, 255),    # Orange
    "Walking"      : (0, 255, 0),      # Green
    "Standing"     : (200, 200, 200),  # Gray
    "⚠ Loitering"  : (0, 0, 255),      # Red
    "⚠ Falling"    : (0, 0, 255),      # Red
    "Initializing" : (100, 100, 100),  # Dark gray
}

class Layer1Visualizer:
    def __init__(self, config: dict):
        cfg               = config.get("output", {})
        self.font         = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale   = cfg.get("font_scale", 0.55)
        self.thickness    = cfg.get("line_thickness", 2)
        self.show_fps     = cfg.get("show_fps", True)
        self.show_count   = cfg.get("show_count", True)
        self.show_action  = cfg.get("show_action", True)
        self.show_conf    = cfg.get("show_confidence", False)

    def draw(self, frame: np.ndarray, tracks: list, pose_data: dict) -> np.ndarray:
        for track in tracks:
            tid        = track["track_id"]
            cls_name   = track["class_name"]
            action     = track.get("action", "")
            conf       = track["confidence"]
            x1, y1, x2, y2 = track["bbox"]

            color = _COLORS[tid % len(_COLORS)]

            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, self.thickness)

            # Corner accents
            corner_len = 15
            cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, 3)
            cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, 3)
            cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, 3)
            cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, 3)
            cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, 3)
            cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, 3)
            cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, 3)
            cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, 3)

            # Label
            conf_str = f" {conf:.0%}" if self.show_conf else ""
            label    = f"#{tid} {cls_name}{conf_str}"
            self._draw_label(frame, label, x1, y1 - 6, color)

            # Action label
            if self.show_action and action and action not in ("Initializing",):
                action_color = ACTION_COLORS.get(action, (200, 200, 200))
                self._draw_label(frame, action, x1, y1 - 26, action_color, alpha=0.7)

        if pose_data:
            from .pose_estimator import SKELETON, SKELETON_COLORS
            kp_threshold = 0.5
            for person_idx, data in pose_data.items():
                kps = data["keypoints"]
                for conn_idx, (i, j) in enumerate(SKELETON):
                    x1p, y1p, c1 = kps[i]
                    x2p, y2p, c2 = kps[j]
                    if c1 > kp_threshold and c2 > kp_threshold:
                        clr = SKELETON_COLORS[conn_idx % len(SKELETON_COLORS)]
                        cv2.line(frame, (int(x1p), int(y1p)), (int(x2p), int(y2p)), clr, 2, cv2.LINE_AA)
                for x, y, c in kps:
                    if c > kp_threshold:
                        cv2.circle(frame, (int(x), int(y)), 4, (255, 255, 255), -1, cv2.LINE_AA)

        if self.show_count:
            self._draw_overlay(frame, f"Objects: {len(tracks)}", 10, 30)

        return frame

    def _draw_label(self, frame, text, x, y, color, alpha=0.85):
        (tw, th), baseline = cv2.getTextSize(text, self.font, self.font_scale, 1)
        y = max(y, th + 4)
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y - th - 4), (x + tw + 6, y + baseline), color, -1)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        cv2.putText(frame, text, (x + 3, y), self.font, self.font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_overlay(self, frame, text, x, y):
        cv2.putText(frame, text, (x, y), self.font, 0.75, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), self.font, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
