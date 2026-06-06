import cv2
import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class TripLine:
    """
    A virtual line defined by two points.
    Counts objects crossing it in either direction.

    direction_label:
        "horizontal" → counts left↔right crossing
        "vertical"   → counts up↓down crossing
        "both"       → counts all crossings
    """
    name            : str
    point_a         : Tuple[int, int]     # Line start (x, y)
    point_b         : Tuple[int, int]     # Line end (x, y)
    color           : Tuple[int,int,int]  = (0, 255, 255)  # cyan default
    count_classes   : List[str]           = field(default_factory=lambda: ["all"])
    direction_label : str                 = "both"         # "in", "out", "both"
    label_in        : str                 = "IN"
    label_out       : str                 = "OUT"


class LineCrossingCounter:
    """
    Detects when tracked objects cross a user-defined line.

    Algorithm:
        For each track, store its previous center position.
        On each frame, check if the line from prev_pos to curr_pos
        intersects the tripline.
        If it does, determine direction using cross product.

    This is the standard algorithm used in:
    - Retail people counters
    - Traffic flow analysis
    - Airport passenger counting
    """

    def __init__(self, config: dict):
        cfg = config.get("lines", {})
        self.lines : List[TripLine] = []

        # Per-line counts: { line_name: {"in": 0, "out": 0} }
        self._counts: Dict[str, Dict[str, int]] = {}

        # Previous positions: { track_id: (cx, cy) }
        self._prev_positions: Dict[int, Tuple[int,int]] = {}

        # Per-track crossed lines this frame (prevent double count)
        self._crossed_this_frame: set = set()

        # Load predefined lines
        for l in cfg.get("predefined_lines", []):
            self.add_line(TripLine(
                name          = l["name"],
                point_a       = tuple(l["point_a"]),
                point_b       = tuple(l["point_b"]),
                color         = tuple(l.get("color", [0, 255, 255])),
                count_classes = l.get("count_classes", ["all"]),
                label_in      = l.get("label_in", "IN"),
                label_out     = l.get("label_out", "OUT")
            ))

    def add_line(self, line: TripLine):
        """Called when user draws a line in the UI."""
        self.lines.append(line)
        self._counts[line.name] = {"in": 0, "out": 0}
        logger.info(f"Tripline added: '{line.name}' from {line.point_a} to {line.point_b}")

    def remove_line(self, name: str):
        self.lines = [l for l in self.lines if l.name != name]
        self._counts.pop(name, None)

    def clear_counts(self, line_name: Optional[str] = None):
        """Reset counters — all lines or a specific one."""
        if line_name:
            self._counts[line_name] = {"in": 0, "out": 0}
        else:
            for name in self._counts:
                self._counts[name] = {"in": 0, "out": 0}

    def update(self, tracks: list) -> Tuple[list, List[str]]:
        """
        Process all tracks against all lines.

        Returns:
            (tracks, crossing_events)
            crossing_events: list of strings describing what crossed
        """
        events     = []
        active_ids = set()
        self._crossed_this_frame.clear()

        for track in tracks:
            tid     = track["track_id"]
            cls_name= track["class_name"]
            x1,y1,x2,y2 = track["bbox"]
            cx      = (x1 + x2) // 2
            cy      = (y1 + y2) // 2
            active_ids.add(tid)

            curr_pos = (cx, cy)
            prev_pos = self._prev_positions.get(tid)

            if prev_pos is not None and prev_pos != curr_pos:
                for line in self.lines:
                    # Check class filter
                    if "all" not in line.count_classes and cls_name not in line.count_classes:
                        continue

                    # Check if path from prev→curr intersects the tripline
                    crossed, direction = self._check_crossing(
                        prev_pos, curr_pos, line.point_a, line.point_b
                    )

                    cross_key = (tid, line.name)
                    if crossed and cross_key not in self._crossed_this_frame:
                        self._crossed_this_frame.add(cross_key)
                        dir_label = line.label_in if direction > 0 else line.label_out
                        self._counts[line.name][
                            "in" if direction > 0 else "out"
                        ] += 1

                        total = sum(self._counts[line.name].values())
                        event = (f"↔ LINE CROSS | {cls_name.upper()} #{tid} "
                                 f"crossed '{line.name}' [{dir_label}] "
                                 f"| Total: {total}")
                        events.append(event)
                        logger.info(event)

            self._prev_positions[tid] = curr_pos

        # Clean up disappeared tracks
        for tid in list(self._prev_positions.keys()):
            if tid not in active_ids:
                del self._prev_positions[tid]

        return tracks, events

    def _check_crossing(
        self,
        p1: Tuple[int,int], p2: Tuple[int,int],
        a:  Tuple[int,int], b:  Tuple[int,int]
    ) -> Tuple[bool, int]:
        """
        Check if segment p1→p2 (track movement) intersects segment a→b (tripline).

        Returns:
            (crossed: bool, direction: int)
            direction: +1 = one side, -1 = other side
            Uses cross product to determine which side of the line the track crossed from.
        """
        def cross(o, u, v):
            return (u[0]-o[0]) * (v[1]-o[1]) - (u[1]-o[1]) * (v[0]-o[0])

        def on_segment(p, q, r):
            return (min(p[0],r[0]) <= q[0] <= max(p[0],r[0]) and
                    min(p[1],r[1]) <= q[1] <= max(p[1],r[1]))

        d1 = cross(a, b, p1)
        d2 = cross(a, b, p2)
        d3 = cross(p1, p2, a)
        d4 = cross(p1, p2, b)

        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            direction = 1 if d1 > 0 else -1
            return True, direction

        # Collinear edge cases
        if d1 == 0 and on_segment(a, p1, b): return True, 1
        if d2 == 0 and on_segment(a, p2, b): return True, -1

        return False, 0

    def get_counts(self) -> Dict[str, Dict[str, int]]:
        """Return all line counts — used by analytics dashboard."""
        return dict(self._counts)

    def get_total(self, line_name: str) -> int:
        counts = self._counts.get(line_name, {})
        return counts.get("in", 0) + counts.get("out", 0)
