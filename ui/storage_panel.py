from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

class StoragePanel(QWidget):
    def __init__(self, analytics, clip_storage):
        super().__init__()
        self.analytics = analytics
        self.clip_storage = clip_storage
        self.setStyleSheet("background: #1a1a1a; color: #e0e0e0; border-radius: 8px;")
        self.setMinimumWidth(320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Storage & Analytics")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # Stats section
        self.lbl_detections = QLabel("Total Detections (24h): 0")
        self.lbl_alerts = QLabel("Total Alerts (24h): 0")
        
        for lbl in [self.lbl_detections, self.lbl_alerts]:
            lbl.setFont(QFont("Segoe UI", 10))
            layout.addWidget(lbl)

        # Toggle Auto-Record
        self.chk_record = QCheckBox("🎥 Auto-Record Video Clips (Away Mode)")
        self.chk_record.setChecked(self.clip_storage.enabled)
        self.chk_record.toggled.connect(self._toggle_recording)
        self.chk_record.setStyleSheet("QCheckBox { font-weight: bold; color: #ff5555; }")
        layout.addWidget(self.chk_record)

        # Refresh button
        btn_refresh = QPushButton("🔄 Refresh Stats")
        btn_refresh.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 6px; padding: 6px;")
        btn_refresh.clicked.connect(self.refresh_stats)
        layout.addWidget(btn_refresh)

        # Table for recent alerts
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Type", "Zone"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("QTableWidget { background: #222; border: 1px solid #444; }")
        layout.addWidget(self.table)

        self.refresh_stats()

    def _toggle_recording(self, checked):
        self.clip_storage.enabled = checked

    def refresh_stats(self):
        # Update summary labels
        dets = self.analytics.total_detections(24)
        alerts = self.analytics.total_alerts(24)
        self.lbl_detections.setText(f"Total Detections (24h): {dets}")
        self.lbl_alerts.setText(f"Total Alerts (24h): {alerts}")

        # Update table
        recent = self.analytics.recent_alerts(10)
        self.table.setRowCount(len(recent))
        for i, row in enumerate(recent):
            time_str = row.get("timestamp", "")[11:19] # Extract HH:MM:SS
            t_item = QTableWidgetItem(time_str)
            t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            type_item = QTableWidgetItem(str(row.get("alert_type", "")))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            zone_item = QTableWidgetItem(str(row.get("zone_name", "")))
            zone_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.table.setItem(i, 0, t_item)
            self.table.setItem(i, 1, type_item)
            self.table.setItem(i, 2, zone_item)
