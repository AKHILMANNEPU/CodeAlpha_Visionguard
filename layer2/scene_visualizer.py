import cv2
import numpy as np
from typing import List, Dict

class SceneVisualizer:
    """
    Draws all Layer 2 annotations onto video frames:
    - Zone polygons with fill + label + occupancy count
    - Triplines with counters
    - Density level badges on zones
    - Dwell time labels on tracks
    """

    def __init__(self, config: dict):
        self.font       = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = 0.55
        self.thickness  = 2

    def draw_zones(
        self,
        frame         : np.ndarray,
        zones         : list,
        occupancy     : Dict[str, int],
        density_levels: Dict[str, str]
    ) -> np.ndarray:
        """Draw all zone polygons with labels."""
        overlay = frame.copy()

        for zone in zones:
            if len(zone.points) < 3:
                continue

            pts   = np.array(zone.points, dtype=np.int32)
            color = zone.color

            # Filled polygon (semi-transparent)
            cv2.fillPoly(overlay, [pts], color)

        # Blend overlay with original
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

        # Draw polygon borders + labels on top (full opacity)
        for zone in zones:
            if len(zone.points) < 3:
                continue

            pts   = np.array(zone.points, dtype=np.int32)
            color = zone.color
            count = occupancy.get(zone.name, 0)
            level = density_levels.get(zone.name, "LOW")

            # Border
            cv2.polylines(frame, [pts], isClosed=True, color=color,
                          thickness=2, lineType=cv2.LINE_AA)

            # Corner dots
            for pt in zone.points:
                cv2.circle(frame, pt, 5, color, -1)

            # Zone name label — positioned at centroid
            cx = int(np.mean([p[0] for p in zone.points]))
            cy = int(np.mean([p[1] for p in zone.points]))

            label    = f"{zone.name}"
            count_lbl= f"Count: {count} | {level}"
            self._draw_text_badge(frame, label,     cx, cy - 12, color)
            self._draw_text_badge(frame, count_lbl, cx, cy + 12, color)

        return frame

    def draw_lines(
        self,
        frame  : np.ndarray,
        lines  : list,
        counts : Dict[str, Dict[str, int]]
    ) -> np.ndarray:
        """Draw all triplines with counters."""
        for line in lines:
            pa = line.point_a
            pb = line.point_b
            c  = line.color

            # Main line
            cv2.line(frame, pa, pb, c, self.thickness + 1, cv2.LINE_AA)
            cv2.circle(frame, pa, 6, c, -1)
            cv2.circle(frame, pb, 6, c, -1)

            # Labels and counts
            cx = (pa[0] + pb[0]) // 2
            cy = (pa[1] + pb[1]) // 2
            
            total_counts = counts.get(line.name, {"in": 0, "out": 0})
            label = f"{line.name}: IN {total_counts['in']} | OUT {total_counts['out']}"
            
            self._draw_text_badge(frame, label, cx, cy, c)
            
        return frame

    def draw_dwell_labels(self, frame: np.ndarray, tracks: list) -> np.ndarray:
        """Draw Dwell Time labels next to bounding boxes."""
        for track in tracks:
            dwell_times = track.get("dwell_times", {})
            if not dwell_times:
                continue
                
            x1, y1, x2, y2 = track["bbox"]
            
            # Find the longest dwell time to display
            longest_zone = max(dwell_times.items(), key=lambda item: item[1]["seconds"], default=None)
            if longest_zone:
                zone_name, data = longest_zone
                label = f"{data['label']} in {zone_name}"
                # Draw at bottom of bounding box
                self._draw_text_badge(frame, label, x1, y2 + 20, (0, 165, 255), alpha=0.7)
                
        return frame

    def _draw_text_badge(self, frame: np.ndarray, text: str, x: int, y: int, color: tuple, alpha: float = 0.85):
        """Helper to draw text with a solid background badge."""
        (tw, th), baseline = cv2.getTextSize(text, self.font, self.font_scale, 1)
        
        # Center the text around (x, y)
        x_adj = x - (tw // 2)
        y_adj = y
        
        y_adj = max(y_adj, th + 4)
        overlay = frame.copy()
        
        cv2.rectangle(overlay, (x_adj - 4, y_adj - th - 4), (x_adj + tw + 4, y_adj + baseline + 2), color, -1)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        cv2.putText(frame, text, (x_adj, y_adj), self.font, self.font_scale, (255, 255, 255), 1, cv2.LINE_AA)
