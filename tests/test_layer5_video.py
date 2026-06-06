import pytest
import os
import sys
import numpy as np
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.video_widget import VideoWidget, PipelineThread

@pytest.fixture
def dummy_frame():
    return np.zeros((720, 1280, 3), dtype=np.uint8)

# =====================================================================
# 4. Multi-Camera Grid Testing
# =====================================================================

def test_single_camera_view(qtbot, dummy_frame):
    """UI-011: Video displayed correctly."""
    widget = VideoWidget()
    qtbot.addWidget(widget)
    
    # Send frame
    widget.update_frame(dummy_frame)
    assert widget.label.pixmap() is not None
    assert not widget.label.pixmap().isNull()

def test_dynamic_camera_addition(qtbot):
    """UI-015: New camera appears instantly (Mock Grid Layout)."""
    from PyQt6.QtWidgets import QWidget, QGridLayout
    parent = QWidget()
    grid = QGridLayout(parent)
    qtbot.addWidget(parent)
    
    # Add 4 cameras
    for i in range(4):
        w = VideoWidget()
        grid.addWidget(w, i // 2, i % 2)
        
    assert grid.count() == 4
    
    # Remove one (UI-016)
    item = grid.takeAt(3)
    widget = item.widget()
    widget.deleteLater()
    
    assert grid.count() == 3

def test_16_camera_grid(qtbot):
    """UI-014: 16 camera grid stable."""
    from PyQt6.QtWidgets import QWidget, QGridLayout
    parent = QWidget()
    grid = QGridLayout(parent)
    qtbot.addWidget(parent)
    
    for i in range(16):
        w = VideoWidget()
        grid.addWidget(w, i // 4, i % 4)
        
    assert grid.count() == 16
