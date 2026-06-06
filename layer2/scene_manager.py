import numpy as np
import logging
from typing import Optional

from .zone_intrusion  import ZoneIntrusionDetector, Zone
from .line_crossing   import LineCrossingCounter, TripLine
from .crowd_density   import CrowdDensityEstimator
from .dwell_time      import DwellTimeAnalyzer
from .heatmap         import HeatmapGenerator
from .scene_visualizer import SceneVisualizer

logger = logging.getLogger(__name__)


class SceneManager:
    """
    Master Layer 2 controller.
    Wraps all 5 scene intelligence components into one process() call.

    Usage:
        scene = SceneManager(config, frame_shape=(720, 1280))

        # In pipeline loop:
        result = scene.process(tracks, frame)
        annotated = result["annotated_frame"]
        alerts    = result["alerts"]
        counts    = result["line_counts"]
    """

    def __init__(self, config: dict):
        logger.info("Initializing Layer 2 Scene Manager...")

        self.config     = config
        self.frame_shape= None

        self.zone_detector = ZoneIntrusionDetector(config)
        self.line_counter  = LineCrossingCounter(config)
        self.crowd_estimator = CrowdDensityEstimator(config)
        self.dwell_analyzer  = DwellTimeAnalyzer(config)
        self.heatmap         = HeatmapGenerator(config, (720, 1280, 3))
        self.visualizer      = SceneVisualizer(config)

        # Toggle flags (controlled from PyQt6 UI)
        self.show_zones    = True
        self.show_lines    = True
        self.show_heatmap  = False    # off by default — user enables
        self.show_dwell    = True
        self.show_density  = True

        logger.info("Layer 2 Scene Manager ready.")

    def process(self, tracks: list, frame: np.ndarray) -> dict:
        if self.frame_shape is None:
            self.frame_shape = frame.shape
            self.heatmap.frame_shape = self.frame_shape

        all_alerts = []

        # ── Step 1: Zone Intrusion ────────────────────────────────────────
        tracks, zone_alerts = self.zone_detector.update(tracks)
        all_alerts.extend(zone_alerts)

        # ── Step 2: Line Crossing ─────────────────────────────────────────
        tracks, line_events = self.line_counter.update(tracks)
        all_alerts.extend(line_events)

        # ── Step 3: Crowd Density ─────────────────────────────────────────
        zone_occupancy = self.zone_detector.get_zone_occupancy()
        density_levels, crowd_alerts = self.crowd_estimator.update(
            tracks, zone_occupancy
        )
        all_alerts.extend(crowd_alerts)

        # ── Step 4: Dwell Time ────────────────────────────────────────────
        tracks, dwell_alerts = self.dwell_analyzer.update(tracks)
        all_alerts.extend(dwell_alerts)

        # ── Step 5: Heatmap Update ────────────────────────────────────────
        self.heatmap.update(tracks)

        # ── Step 6: Draw everything ───────────────────────────────────────
        annotated = frame.copy()

        if self.show_heatmap:
            annotated = self.heatmap.render(annotated)

        if self.show_zones:
            annotated = self.visualizer.draw_zones(
                annotated,
                self.zone_detector.zones,
                zone_occupancy,
                density_levels
            )

        if self.show_lines:
            annotated = self.visualizer.draw_lines(
                annotated,
                self.line_counter.lines,
                self.line_counter.get_counts()
            )

        if self.show_dwell:
            annotated = self.visualizer.draw_dwell_labels(
                annotated, tracks
            )

        return {
            "tracks"          : tracks,
            "alerts"          : all_alerts,
            "line_counts"     : self.line_counter.get_counts(),
            "density_levels"  : density_levels,
            "dwell_alerts"    : dwell_alerts,
            "annotated_frame" : annotated
        }

    # ── Passthrough helpers for UI ────────────────────────────────────────

    def add_zone(self, zone: Zone):
        self.zone_detector.add_zone(zone)

    def add_line(self, line: TripLine):
        self.line_counter.add_line(line)

    def clear_zones(self):
        self.zone_detector.clear_zones()

    def clear_lines(self):
        self.line_counter.lines.clear()
        self.line_counter._counts.clear()

    def reset_counts(self):
        self.line_counter.clear_counts()

    def reset_heatmap(self):
        self.heatmap.reset()

    def save_heatmap(self, path: str, frame=None):
        self.heatmap.save(path, frame)
