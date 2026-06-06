import pytest
import os
import sys
from PyQt6.QtCore import Qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.zone_editor import ZoneEditor

# =====================================================================
# 5. Zone Drawing & 6. Line Crossing Testing
# =====================================================================

def test_draw_polygon_zone_mode(qtbot):
    """UI-021: Verify clicking zone button activates zone mode."""
    editor = ZoneEditor()
    qtbot.addWidget(editor)
    
    # Simulate button click
    qtbot.mouseClick(editor.btn_zone, Qt.MouseButton.LeftButton)
    assert editor.current_mode == "zone"
    
def test_draw_trip_line_mode(qtbot):
    """UI-031: Verify clicking line button activates line mode."""
    editor = ZoneEditor()
    qtbot.addWidget(editor)
    
    qtbot.mouseClick(editor.btn_line, Qt.MouseButton.LeftButton)
    assert editor.current_mode == "line"

def test_cancel_drawing_mode(qtbot):
    """Verify cancellation clears mode and points."""
    editor = ZoneEditor()
    qtbot.addWidget(editor)
    
    editor.set_mode("zone")
    editor.handle_click(10, 10)
    assert len(editor.points) == 1
    
    qtbot.mouseClick(editor.btn_cancel, Qt.MouseButton.LeftButton)
    assert editor.current_mode == "none"
    assert len(editor.points) == 0

def test_zone_creation_signals(qtbot):
    """UI-024: Validate that drawing multiple points yields a Zone object."""
    editor = ZoneEditor()
    qtbot.addWidget(editor)
    editor.name_input.setText("TestZone")
    
    with qtbot.waitSignal(editor.zone_created, timeout=1000) as blocker:
        editor.set_mode("zone")
        editor.handle_click(0, 0)
        editor.handle_click(100, 0)
        editor.handle_click(100, 100)
        editor.handle_click(0, 100)
        # 5th click close to start point closes the polygon
        editor.handle_click(0, 2) 
        
    zone_obj = blocker.args[0]
    assert zone_obj.name == "TestZone"
    assert len(zone_obj.points) == 4
