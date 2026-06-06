import cv2
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class HeatmapGenerator:
    """
    Generates a cumulative activity heatmap from track positions.

    Every frame, all track centers are added as Gaussian blobs
    to an accumulator. Over time this shows WHERE objects spend
    the most time in the scene.

    Visualization modes:
    - "overlay"  : semi-transparent heatmap over live video
    - "standalone": pure heatmap without video
    - "blend"    : 50/50 blend of video + heatmap

    Use cases:
    - Retail: identify which store sections get most traffic
    - Security: find surveillance blind spots (no activity areas)
    - Traffic: identify congestion hotspots
    - Smart cities: pedestrian flow analysis
    """

    def __init__(self, config: dict, frame_shape: tuple):
        """
        Args:
            config     : full config dict
            frame_shape: (height, width) of video frame
        """
        cfg = config.get("heatmap", {})
        self.enabled       = cfg.get("enabled", True)
        self.alpha         = cfg.get("overlay_alpha", 0.4)
        self.decay_factor  = cfg.get("decay_factor", 0.995)   # per-frame decay
        self.blob_radius   = cfg.get("blob_radius", 25)        # Gaussian spread
        self.colormap      = cfg.get("colormap", "JET")        # or TURBO, HOT
        self.mode          = cfg.get("mode", "overlay")
        self.classes       = cfg.get("track_classes", ["person"])
        self.normalize_max = cfg.get("normalize_max", 0.8)     # avoid saturation

        h, w = frame_shape[:2]
        self._accumulator = np.zeros((h, w), dtype=np.float32)
        self._frame_count = 0
        self._h = h
        self._w = w

    @property
    def frame_shape(self):
        return (self._h, self._w)
        
    @frame_shape.setter
    def frame_shape(self, shape):
        h, w = shape[:2]
        if h != self._h or w != self._w:
            logger.info(f"Resizing heatmap from {self._w}x{self._h} to {w}x{h}")
            if self._accumulator is not None and self._accumulator.sum() > 0:
                self._accumulator = cv2.resize(self._accumulator, (w, h))
            else:
                self._accumulator = np.zeros((h, w), dtype=np.float32)
            self._h = h
            self._w = w

        # Precompute Gaussian kernel for efficiency
        k_size = self.blob_radius * 4 + 1
        if k_size % 2 == 0:
            k_size += 1
        self._kernel = cv2.getGaussianKernel(k_size, self.blob_radius)
        self._kernel_2d = self._kernel @ self._kernel.T

        # Map colormap name to cv2 constant
        self._cm_map = {
            "JET"  : cv2.COLORMAP_JET,
            "TURBO": cv2.COLORMAP_TURBO,
            "HOT"  : cv2.COLORMAP_HOT,
            "BONE" : cv2.COLORMAP_BONE,
            "INFERNO": cv2.COLORMAP_INFERNO
        }

        logger.info(f"Heatmap initialized: {w}x{h}, mode={self.mode}")

    def update(self, tracks: list):
        """
        Add current track positions to accumulator.
        Call this every frame regardless of display state.
        """
        if not self.enabled:
            return

        self._frame_count += 1

        # Decay: older activity fades gradually
        self._accumulator *= self.decay_factor

        for track in tracks:
            cls_name = track["class_name"]
            if "all" not in self.classes and cls_name not in self.classes:
                continue

            cx, cy = track["center"]

            # Clamp to frame bounds
            cx = max(0, min(cx, self._w - 1))
            cy = max(0, min(cy, self._h - 1))

            # Add Gaussian blob at track center
            self._add_gaussian(cx, cy)

    def _add_gaussian(self, cx: int, cy: int):
        """Paint a Gaussian blob onto the accumulator at (cx, cy)."""
        k = self._kernel_2d
        kh, kw = k.shape
        kh2, kw2 = kh // 2, kw // 2

        # Compute valid region (handle boundary)
        x1 = max(cx - kw2, 0)
        y1 = max(cy - kh2, 0)
        x2 = min(cx + kw2 + 1, self._w)
        y2 = min(cy + kh2 + 1, self._h)

        kx1 = x1 - (cx - kw2)
        ky1 = y1 - (cy - kh2)
        kx2 = kx1 + (x2 - x1)
        ky2 = ky1 + (y2 - y1)

        if x2 > x1 and y2 > y1 and kx2 > kx1 and ky2 > ky1:
            self._accumulator[y1:y2, x1:x2] += k[ky1:ky2, kx1:kx2]

    def render(self, frame: np.ndarray) -> np.ndarray:
        """
        Render heatmap onto the frame.

        Args:
            frame: BGR frame from Layer 1

        Returns:
            Frame with heatmap applied
        """
        if not self.enabled or self._accumulator.max() < 1e-6:
            return frame

        # Normalize accumulator to 0-255
        norm = self._accumulator.copy()
        norm_max = norm.max()
        if norm_max > 0:
            norm = np.clip(norm / (norm_max * self.normalize_max), 0, 1)
        norm_uint8 = (norm * 255).astype(np.uint8)

        # Apply colormap
        colormap_id = self._cm_map.get(self.colormap, cv2.COLORMAP_JET)
        heatmap_bgr = cv2.applyColorMap(norm_uint8, colormap_id)

        # Mask: only show heatmap where there was activity
        mask = norm_uint8 > 10
        mask_3ch = np.stack([mask, mask, mask], axis=-1)

        if self.mode == "standalone":
            return heatmap_bgr

        elif self.mode == "blend":
            return cv2.addWeighted(frame, 0.6, heatmap_bgr, 0.4, 0)

        else:  # "overlay" — default
            result = frame.copy()
            result[mask_3ch] = cv2.addWeighted(
                frame, 1 - self.alpha,
                heatmap_bgr, self.alpha, 0
            )[mask_3ch]
            return result

    def reset(self):
        """Clear accumulator — reset heatmap."""
        self._accumulator.fill(0)
        self._frame_count = 0
        logger.info("Heatmap reset.")

    def save(self, path: str, frame: Optional[np.ndarray] = None):
        """Save heatmap image to disk."""
        if frame is not None:
            img = self.render(frame)
        else:
            norm = self._accumulator / max(self._accumulator.max(), 1e-6)
            img  = cv2.applyColorMap(
                (norm * 255).astype(np.uint8),
                self._cm_map.get(self.colormap, cv2.COLORMAP_JET)
            )
        cv2.imwrite(path, img)
        logger.info(f"Heatmap saved to {path}")
