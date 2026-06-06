import cv2
import os
import numpy as np
import logging
from datetime  import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox,
    QSlider, QFileDialog
)
from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QImage, QPixmap, QFont

logger = logging.getLogger(__name__)


class HeatmapViewer(QWidget):
    """
    Displays the live heatmap from Layer 2's HeatmapGenerator.

    Features:
    - Live heatmap preview updated on demand
    - Opacity slider for overlay transparency
    - Colormap selector (JET, TURBO, HOT, INFERNO)
    - Save heatmap to PNG/JPEG
    - Reset heatmap accumulator button
    """

    save_requested = pyqtSignal(str)   # emits save path

    def __init__(self, heatmap_generator, config: dict, parent=None):
        super().__init__(parent)
        self.heatmap    = heatmap_generator
        self.config     = config
        self._last_frame= None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Title
        title = QLabel("Activity Heatmap")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color:#e0e0e0;")
        layout.addWidget(title)

        # Heatmap display label
        self.heatmap_label = QLabel("No heatmap data yet")
        self.heatmap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heatmap_label.setMinimumHeight(300)
        self.heatmap_label.setStyleSheet(
            "background:#0a0a0a; border:1px solid #333; border-radius:4px;"
            "color:#555; font-size:13px;"
        )
        layout.addWidget(self.heatmap_label, stretch=1)

        # Controls row 1 — colormap + opacity
        ctrl1 = QHBoxLayout()
        ctrl1.addWidget(QLabel("Colormap:"))

        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(["JET", "TURBO", "HOT", "INFERNO", "BONE"])
        self.cmap_combo.setCurrentText(
            self.config.get("heatmap", {}).get("colormap", "JET")
        )
        self.cmap_combo.setStyleSheet(
            "QComboBox{background:#222;color:#ddd;border:1px solid #444;"
            "border-radius:4px;padding:3px;}"
        )
        self.cmap_combo.currentTextChanged.connect(self._on_cmap_changed)
        ctrl1.addWidget(self.cmap_combo)

        ctrl1.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 90)
        self.opacity_slider.setValue(
            int(self.config.get("heatmap", {}).get("overlay_alpha", 0.4) * 100)
        )
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        ctrl1.addWidget(self.opacity_slider)
        layout.addLayout(ctrl1)

        # Controls row 2 — mode + buttons
        ctrl2 = QHBoxLayout()
        ctrl2.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["overlay", "blend", "standalone"])
        self.mode_combo.setStyleSheet(
            "QComboBox{background:#222;color:#ddd;border:1px solid #444;"
            "border-radius:4px;padding:3px;}"
        )
        self.mode_combo.currentTextChanged.connect(
            lambda m: setattr(self.heatmap, "mode", m)
        )
        ctrl2.addWidget(self.mode_combo)
        layout.addLayout(ctrl2)

        # Action buttons
        btn_row = QHBoxLayout()
        for text, slot in [
            ("🔄 Refresh", self.refresh),
            ("💾 Save PNG", self._save_heatmap),
            ("↺ Reset",    self._reset_heatmap)
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(
                "QPushButton{background:#2a2a2a;border:1px solid #444;"
                "border-radius:5px;padding:6px;font-size:12px;}"
                "QPushButton:hover{background:#333;}"
            )
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        # Stats label
        self.stats_label = QLabel("Frames accumulated: 0")
        self.stats_label.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(self.stats_label)

    def set_latest_frame(self, frame: np.ndarray):
        """Feed latest video frame for overlay rendering."""
        self._last_frame = frame.copy()

    def refresh(self):
        """Render current heatmap and display in widget."""
        try:
            if self._last_frame is None:
                return

            rendered = self.heatmap.render(self._last_frame)
            self._display_frame(rendered)

            frames = self.heatmap._frame_count
            self.stats_label.setText(f"Frames accumulated: {frames:,}")
        except Exception as e:
            logger.debug(f"HeatmapViewer refresh error: {e}")

    def _display_frame(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qi  = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        px  = QPixmap.fromImage(qi).scaled(
            self.heatmap_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.heatmap_label.setPixmap(px)

    def _on_cmap_changed(self, name: str):
        self.heatmap.colormap = name
        self.refresh()

    def _on_opacity_changed(self, value: int):
        self.heatmap.alpha = value / 100.0
        self.refresh()

    def _save_heatmap(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Heatmap", "heatmap.png",
            "Images (*.png *.jpg)"
        )
        if path and self._last_frame is not None:
            try:
                self.heatmap.save(path, self._last_frame)
                self.save_requested.emit(path)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Error", f"Failed to save heatmap:\n{e}")

    def _reset_heatmap(self):
        self.heatmap.reset()
        self.heatmap_label.setText("Heatmap reset")
        self.heatmap_label.setPixmap(QPixmap())
        self.stats_label.setText("Frames accumulated: 0")
