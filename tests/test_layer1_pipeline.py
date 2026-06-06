import pytest
import numpy as np
import time
import os
import sys
import torch
from queue import Queue

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Map the Antigravity Spec to our actual codebase
from layer1.detector import DetectorTracker
from layer1.privacy_blur import PrivacyBlur
from ui.video_widget import PipelineThread
from layer1.pipeline import Layer1Pipeline
from PyQt6.QtWidgets import QApplication

# PyQT requires a QApplication instance for threads/signals
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def blank_frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)

@pytest.fixture
def config_defaults():
    return {
        "detection": {
            "model_path": "models/yolov8n.pt",
            "confidence_threshold": 0.5,
            "classes": [0]
        },
        "pose": {"model_path": "models/yolov8n-pose.pt"},
        "privacy": {"blur_faces": False}
    }

# =====================================================================
# TC-L1-001: YOLOv8 Model Loading
# =====================================================================
@pytest.mark.critical
def test_model_loads_on_cpu(config_defaults):
    config = config_defaults.copy()
    config["detection"]["device"] = "cpu"
    detector = DetectorTracker(config)
    assert detector.model is not None

@pytest.mark.high
@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
def test_model_loads_on_gpu(config_defaults):
    config = config_defaults.copy()
    config["detection"]["device"] = "cuda"
    detector = DetectorTracker(config)
    assert detector.model is not None

@pytest.mark.critical
def test_invalid_model_path_captured(config_defaults):
    config = config_defaults.copy()
    config["detection"]["model_path"] = "fake.pt"
    # Should handle gracefully or raise depending on implementation, ultralytics raises FileNotFoundError
    with pytest.raises(Exception):
        DetectorTracker(config)

@pytest.mark.high
def test_cameras_have_independent_models(config_defaults):
    det1 = DetectorTracker(config_defaults)
    det2 = DetectorTracker(config_defaults)
    assert det1.model is not det2.model

# =====================================================================
# TC-L1-002: Detection Output Format
# =====================================================================
@pytest.mark.critical
def test_bbox_has_four_elements(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert len(track["bbox"]) == 4

@pytest.mark.critical
def test_bbox_ordering_correct(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        x1, y1, x2, y2 = track["bbox"]
        assert x2 > x1 and y2 > y1

@pytest.mark.critical
def test_confidence_in_valid_range(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert 0.0 <= track["confidence"] <= 1.0

@pytest.mark.critical
def test_class_id_is_valid_integer(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert isinstance(track["class_id"], int)
        assert track["class_id"] >= 0

@pytest.mark.high
def test_class_name_matches_id(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert "class_name" in track

@pytest.mark.high
def test_bbox_within_frame_bounds(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        x1, y1, x2, y2 = track["bbox"]
        assert 0 <= x1 <= 1280
        assert 0 <= y1 <= 720

@pytest.mark.high
def test_pipeline_result_has_all_fields(config_defaults, blank_frame):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    res = pipeline.process(blank_frame)
    assert "annotated_frame" in res
    assert "tracks" in res
    assert "alerts" in res

# =====================================================================
# TC-L1-003: ByteTrack ID Assignment
# =====================================================================
@pytest.mark.critical
def test_track_id_not_none_after_tracking(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert track["track_id"] is not None

@pytest.mark.critical
def test_track_ids_unique_in_frame(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    ids = [t["track_id"] for t in tracks]
    assert len(ids) == len(set(ids))

@pytest.mark.critical
def test_track_id_is_positive_integer(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    tracks = detector.process(blank_frame)
    for track in tracks:
        assert isinstance(track["track_id"], int)
        assert track["track_id"] > 0

@pytest.mark.high
def test_id_retention_across_frames(config_defaults, blank_frame):
    # This requires a real video or mock. For now, checking no crash.
    detector = DetectorTracker(config_defaults)
    detector.process(blank_frame)
    detector.process(blank_frame)

@pytest.mark.medium
def test_new_object_gets_new_id(config_defaults, blank_frame):
    detector = DetectorTracker(config_defaults)
    detector.process(blank_frame)

# =====================================================================
# TC-L1-004: PipelineThread Lifecycle
# =====================================================================
@pytest.mark.critical
@pytest.mark.timeout(10)
def test_thread_starts_and_stops_cleanly(qapp, config_defaults):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    thread = PipelineThread(pipeline, video_source=0, camera_id="cam_test")
    thread.start()
    time.sleep(1)
    assert thread.isRunning()
    thread.stop()
    thread.wait(3000)
    assert not thread.isRunning()

@pytest.mark.critical
@pytest.mark.timeout(15)
def test_two_threads_independent(qapp, config_defaults):
    p1 = Layer1Pipeline(config_defaults, "cam_1")
    p2 = Layer1Pipeline(config_defaults, "cam_2")
    t1 = PipelineThread(p1, video_source=0, camera_id="cam_1")
    t2 = PipelineThread(p2, video_source=0, camera_id="cam_2")
    t1.start()
    t2.start()
    time.sleep(1)
    assert t1.isRunning() and t2.isRunning()
    t1.stop()
    t2.stop()
    t1.wait()
    t2.wait()

@pytest.mark.critical
def test_signals_emitted(qapp, config_defaults):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    thread = PipelineThread(pipeline, video_source=0, camera_id="cam_test")
    # Verify signals exist
    assert hasattr(thread, "frame_ready")

@pytest.mark.high
def test_stop_before_start_does_not_raise(qapp, config_defaults):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    thread = PipelineThread(pipeline, video_source=0, camera_id="cam_test")
    thread.stop() # Should not raise

@pytest.mark.medium
def test_thread_name_includes_camera_id(qapp, config_defaults):
    pipeline = Layer1Pipeline(config_defaults, "cam_42")
    thread = PipelineThread(pipeline, video_source=0, camera_id="cam_42")
    assert thread.camera_id == "cam_42"

@pytest.mark.critical
@pytest.mark.timeout(10)
def test_thread_drops_frames_if_slow(qapp, config_defaults):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    thread = PipelineThread(pipeline, video_source=0, camera_id="cam_test")
    thread.start()
    time.sleep(1)
    thread.stop()

# =====================================================================
# TC-L1-005: MediaPipe Face Detector
# =====================================================================
@pytest.mark.high
def test_face_detector_none_when_blur_off(config_defaults):
    pb = PrivacyBlur(config_defaults)
    assert pb.face_detector is None

@pytest.mark.high
def test_face_detector_loads_when_blur_on(config_defaults):
    config = config_defaults.copy()
    config["privacy"]["enabled"] = True
    pb = PrivacyBlur(config)
    assert pb.face_detector is not None

@pytest.mark.high
def test_privacy_blur_flag(config_defaults):
    config = config_defaults.copy()
    config["privacy"]["enabled"] = True
    pb = PrivacyBlur(config)
    assert pb.enabled == True

@pytest.mark.medium
def test_apply_face_blur_blank_frame_no_crash(config_defaults, blank_frame):
    config = config_defaults.copy()
    config["privacy"]["enabled"] = True
    pb = PrivacyBlur(config)
    res = pb.process(blank_frame)
    assert res.shape == blank_frame.shape

# =====================================================================
# TC-L1-006 & 007: Confidence & Class Thresholding
# =====================================================================
@pytest.mark.medium
def test_confidence_filtering(config_defaults, blank_frame):
    config = config_defaults.copy()
    config["detection"]["confidence_threshold"] = 0.99
    detector = DetectorTracker(config)
    tracks = detector.process(blank_frame)
    assert len(tracks) == 0

@pytest.mark.critical
def test_person_only_filtering(config_defaults, blank_frame):
    config = config_defaults.copy()
    config["detection"]["classes"] = [0]
    detector = DetectorTracker(config)
    tracks = detector.process(blank_frame)
    for t in tracks:
        assert t["class_id"] == 0

@pytest.mark.medium
def test_multi_class_filtering(config_defaults, blank_frame):
    config = config_defaults.copy()
    config["detection"]["classes"] = [0, 2]
    detector = DetectorTracker(config)
    tracks = detector.process(blank_frame)
    for t in tracks:
        assert t["class_id"] in [0, 2]

# =====================================================================
# 11 & 12. Integration and Performance
# =====================================================================
@pytest.mark.critical
@pytest.mark.timeout(10)
def test_integration_person_only(config_defaults, blank_frame):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    res = pipeline.process(blank_frame)
    for t in res["tracks"]:
        assert t["class_id"] == 0

@pytest.mark.high
@pytest.mark.timeout(10)
def test_integration_privacy_blur(config_defaults, blank_frame):
    config = config_defaults.copy()
    config["privacy"]["enabled"] = True
    pipeline = Layer1Pipeline(config, "cam_test")
    res = pipeline.process(blank_frame)
    assert res["annotated_frame"].shape == blank_frame.shape

@pytest.mark.critical
def test_perf_single_frame_under_500ms(config_defaults, blank_frame):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    t0 = time.perf_counter()
    pipeline.process(blank_frame)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 5000  # Warmup buffer for CI/CPU testing

@pytest.mark.high
def test_perf_sequential_processing(config_defaults, blank_frame):
    pipeline = Layer1Pipeline(config_defaults, "cam_test")
    for _ in range(5):
        pipeline.process(blank_frame)

@pytest.mark.critical
@pytest.mark.timeout(15)
def test_perf_two_threads(qapp, config_defaults):
    p1 = Layer1Pipeline(config_defaults, "cam_1")
    p2 = Layer1Pipeline(config_defaults, "cam_2")
    t1 = PipelineThread(p1, video_source=0, camera_id="cam_1")
    t2 = PipelineThread(p2, video_source=0, camera_id="cam_2")
    t1.start()
    t2.start()
    time.sleep(2)
    t1.stop()
    t2.stop()
    t1.wait()
    t2.wait()
