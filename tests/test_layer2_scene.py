import pytest
import numpy as np
import cv2
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer2.scene_manager import SceneManager
from layer2.zone_intrusion import ZoneIntrusionDetector, Zone
from layer2.heatmap import HeatmapGenerator
from layer2.line_crossing import LineCrossingCounter, TripLine

@pytest.fixture
def blank_frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)

@pytest.fixture
def config_defaults():
    return {
        "zones": {"alert_cooldown_seconds": 0},
        "heatmap": {"enabled": True, "decay_factor": 0.995},
        "lines": {}
    }

# =====================================================================
# TC-L2-001 & TC-L2-002: pointPolygonTest accuracy
# =====================================================================
@pytest.mark.critical
def test_point_polygon_test_inside_and_outside():
    # Square zone: 100,100 to 300,300
    points = np.array([[100, 100], [300, 100], [300, 300], [100, 300]], dtype=np.int32)
    
    inside_pt = (200, 200)
    outside_pt = (400, 400)
    edge_pt = (100, 200)

    # cv2.pointPolygonTest returns >0 for inside, <0 for outside, 0 for edge
    assert cv2.pointPolygonTest(points, inside_pt, False) > 0
    assert cv2.pointPolygonTest(points, outside_pt, False) < 0
    assert cv2.pointPolygonTest(points, edge_pt, False) == 0

# =====================================================================
# TC-L2-003: Bottom-center coordinate extraction
# =====================================================================
# Replaced test_bottom_center_math with implicit test
@pytest.mark.high
def test_bottom_center_math_implicit(config_defaults):
    # Tests that the system uses the bottom-center (feet) to detect zone entry, not the top.
    detector = ZoneIntrusionDetector(config_defaults)
    # Zone is at y=400 to 500
    z1 = Zone(name="FeetZone", points=[(0,400), (200,400), (200,500), (0,500)])
    detector.zones.append(z1)
    
    # Track with top at 100, bottom at 400. Center is 250, bottom is 400.
    tracks = [{"track_id": 1, "bbox": [100, 100, 200, 400], "class_id": 0, "class_name": "person"}]
    _, alerts = detector.update(tracks)
    # Bottom touches 400, so it should enter.
    assert len(alerts) > 0
    assert "FeetZone" in alerts[0]

# =====================================================================
# TC-L2-004: Zone Overlaps
# =====================================================================
@pytest.mark.high
def test_zone_overlap(config_defaults):
    detector = ZoneIntrusionDetector(config_defaults)
    
    # Zone 1: Left half of screen
    z1 = Zone(name="Left", points=[(0,0), (640,0), (640,720), (0,720)])
    # Zone 2: Top half of screen
    z2 = Zone(name="Top", points=[(0,0), (1280,0), (1280,360), (0,360)])
    
    detector.zones.extend([z1, z2])
    
    # Point at (320, 180) is in both Left and Top zones
    tracks = [{"track_id": 1, "bbox": [300, 100, 340, 180], "class_id": 0, "class_name": "person"}]
    
    updated_tracks, alerts = detector.update(tracks)
    
    assert len(alerts) == 2
    alert_text = " ".join(alerts)
    assert "Left" in alert_text
    assert "Top" in alert_text
    
    # Check that track dict was updated with BOTH zones
    assert "Left" in updated_tracks[0]["zones"]
    assert "Top" in updated_tracks[0]["zones"]

# =====================================================================
# TC-L2-005: Heatmap Accumulation & Decay
# =====================================================================
@pytest.mark.medium
def test_heatmap_accumulation(config_defaults):
    hm = HeatmapGenerator(config_defaults, (720, 1280, 3))
    hm.frame_shape = (720, 1280, 3)
    
    tracks = [{"bbox": [100, 100, 200, 200], "center": (150, 150), "class_id": 0, "class_name": "person"}]
    
    sum_before = hm._accumulator.sum()
    hm.update(tracks)
    sum_after_1 = hm._accumulator.sum()
    
    assert sum_after_1 > sum_before
    
    # Second frame, same track position, accumulation should increase further
    hm.update(tracks)
    sum_after_2 = hm._accumulator.sum()
    
    # The gaussian is added again, but the decay is also applied (0.995 * sum_after_1 + new_gaussian)
    # Since we add a fresh gaussian, it should be significantly higher
    assert sum_after_2 > sum_after_1

@pytest.mark.medium
def test_heatmap_decay_over_frames(config_defaults):
    # If no tracks are present, the heatmap should decay
    hm = HeatmapGenerator(config_defaults, (720, 1280, 3))
    hm.frame_shape = (720, 1280, 3)
    tracks = [{"bbox": [100, 100, 200, 200], "center": (150, 150), "class_id": 0, "class_name": "person"}]
    hm.update(tracks)
    
    peak_sum = hm._accumulator.sum()
    
    # Update with empty tracks
    hm.update([])
    decayed_sum = hm._accumulator.sum()
    
    assert decayed_sum < peak_sum
    # Exact decay factor test
    assert np.isclose(decayed_sum, peak_sum * hm.decay_factor, rtol=1e-3)

# =====================================================================
# TC-L2-006: Line Crossing Direction
# =====================================================================
@pytest.mark.high
def test_line_crossing_direction(config_defaults):
    counter = LineCrossingCounter(config_defaults)
    
    # Vertical trip line down the middle
    line = TripLine(name="Middle", point_a=(640, 0), point_b=(640, 720))
    counter.add_line(line)
    
    # Frame 1: Object on the left
    tracks_f1 = [{"track_id": 1, "bbox": [500, 300, 600, 400], "class_name": "person"}]
    updated, alerts = counter.update(tracks_f1)
    counts = counter.get_counts()
    assert counts["Middle"]["in"] == 0
    assert counts["Middle"]["out"] == 0
    
    # Frame 2: Object crossed to the right
    tracks_f2 = [{"track_id": 1, "bbox": [700, 300, 800, 400], "class_name": "person"}]
    updated, alerts = counter.update(tracks_f2)
    counts = counter.get_counts()
    
    # Depending on orientation, it counts as 'in' or 'out'
    # The cross product math should detect exactly one cross event
    total_crosses = counts["Middle"]["in"] + counts["Middle"]["out"]
    assert total_crosses == 1

# =====================================================================
# TC-L2-007: Empty Zone false alerts
# =====================================================================
@pytest.mark.critical
def test_empty_zone_no_alerts(config_defaults):
    detector = ZoneIntrusionDetector(config_defaults)
    z1 = Zone(name="Empty", points=[(0,0), (100,0), (100,100), (0,100)])
    detector.zones.append(z1)
    
    # Send empty tracks
    tracks, alerts = detector.update([])
    
    assert len(alerts) == 0
    assert len(tracks) == 0

# =====================================================================
# Extra Robustness Cases
# =====================================================================
@pytest.mark.high
def test_object_exiting_zone_triggers_exit_alert(config_defaults):
    detector = ZoneIntrusionDetector(config_defaults)
    # Note: alert_on_exit enabled
    z1 = Zone(name="Box", points=[(100,100), (300,100), (300,300), (100,300)], alert_on_exit=True)
    detector.zones.append(z1)
    
    # Frame 1: Object is inside the zone
    t1 = [{"track_id": 1, "bbox": [150, 150, 200, 200], "class_id": 0, "class_name": "person"}]
    updated, alerts_in = detector.update(t1)
    
    assert len(alerts_in) == 1
    assert "ENTRY" in alerts_in[0]
    
    # Frame 2: Object is outside the zone
    t2 = [{"track_id": 1, "bbox": [400, 400, 500, 500], "class_id": 0, "class_name": "person"}]
    updated, alerts_out = detector.update(t2)
    
    assert len(alerts_out) == 1
    assert "EXIT" in alerts_out[0]

@pytest.mark.critical
def test_scene_manager_full_integration(config_defaults, blank_frame):
    scene = SceneManager(config_defaults)
    scene.zone_detector.zones.append(Zone(name="Z1", points=[(0,0), (10,0), (10,10), (0,10)]))
    
    tracks = [{"track_id": 1, "bbox": [2, 2, 8, 8], "center": (5, 5), "class_id": 0, "class_name": "person"}]
    
    result = scene.process(tracks, blank_frame)
    
    assert "alerts" in result
    assert len(result["alerts"]) == 1
    assert "Z1" in result["alerts"][0]
    assert "annotated_frame" in result
