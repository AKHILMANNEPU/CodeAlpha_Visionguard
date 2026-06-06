from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QLineEdit, QDialog
from PyQt6.QtCore import Qt, pyqtSignal
import logging
from layer2.zone_intrusion import Zone
from layer2.line_crossing import TripLine

logger = logging.getLogger(__name__)

class ZoneEditor(QWidget):
    """
    A floating or dockable widget that allows users to switch the VideoWidget 
    into 'drawing mode' to create Zones and Lines.
    """
    mode_changed = pyqtSignal(str) # "zone", "line", "none"
    zone_created = pyqtSignal(Zone)
    line_created = pyqtSignal(TripLine)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #222; border-radius: 8px;")
        
        layout = QVBoxLayout(self)
        
        title = QLabel("Drawing Tools")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #fff;")
        layout.addWidget(title)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter name (e.g. Zone A)")
        self.name_input.setStyleSheet("color: white; background-color: #333; padding: 4px; border: 1px solid #555;")
        layout.addWidget(self.name_input)
        
        btn_layout = QHBoxLayout()
        self.btn_zone = QPushButton("Draw Zone (Polygon)")
        self.btn_line = QPushButton("Draw Trip Line")
        self.btn_cancel = QPushButton("Cancel")
        
        for btn in [self.btn_zone, self.btn_line, self.btn_cancel]:
            btn.setStyleSheet("background: #333; padding: 6px; border-radius: 4px;")
            btn_layout.addWidget(btn)
            
        layout.addLayout(btn_layout)
        
        self.btn_zone.clicked.connect(lambda: self.set_mode("zone"))
        self.btn_line.clicked.connect(lambda: self.set_mode("line"))
        self.btn_cancel.clicked.connect(lambda: self.set_mode("none"))
        
        self.current_mode = "none"
        self.points = []

    def set_mode(self, mode: str):
        self.current_mode = mode
        self.points = []
        if mode == "zone":
            self.btn_zone.setStyleSheet("background: #0078D7; padding: 6px; border-radius: 4px;")
            self.btn_line.setStyleSheet("background: #333; padding: 6px; border-radius: 4px;")
        elif mode == "line":
            self.btn_line.setStyleSheet("background: #0078D7; padding: 6px; border-radius: 4px;")
            self.btn_zone.setStyleSheet("background: #333; padding: 6px; border-radius: 4px;")
        else:
            self.btn_line.setStyleSheet("background: #333; padding: 6px; border-radius: 4px;")
            self.btn_zone.setStyleSheet("background: #333; padding: 6px; border-radius: 4px;")
            
        self.mode_changed.emit(mode)

    def handle_click(self, x: int, y: int):
        if self.current_mode == "none":
            return
            
        self.points.append((x, y))
        name = self.name_input.text() or f"New {self.current_mode.title()}"
        
        if self.current_mode == "line" and len(self.points) == 2:
            line = TripLine(name=name, point_a=self.points[0], point_b=self.points[1])
            self.line_created.emit(line)
            self.set_mode("none")
            
        elif self.current_mode == "zone" and len(self.points) >= 3:
            # For simplicity, finish zone on 4th click
            if len(self.points) == 4:
                zone = Zone(name=name, points=list(self.points))
                self.zone_created.emit(zone)
                self.set_mode("none")
