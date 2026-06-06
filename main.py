import sys
import yaml
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTabWidget, QStatusBar,
    QGroupBox, QGridLayout, QCheckBox, QSlider, QScrollArea
)
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QFont

from layer1.pipeline  import Layer1Pipeline
from layer4.notification_manager import NotificationManager
from layer5.dashboard_manager import DashboardManager
from ui.dashboard_window import DashboardWindow
from ui.video_widget  import VideoWidget, PipelineThread
from ui.zone_editor   import ZoneEditor
from ui.storage_panel import StoragePanel
from ui.alert_settings_panel import AlertSettingsPanel

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("main")

def load_config(path="config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config   = load_config()
        
        # Will pass self (QMainWindow) to NotificationManager to allow tray icon actions
        self.notification_mgr = None
        self.thread   = None

        self.dashboard_mgr = None
        self.dashboard_window = None

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(8)

        # ── Left: Video Display Grid ──────────────────────────────────────
        self.video_container = QWidget()
        self.video_grid = QGridLayout(self.video_container)
        self.video_grid.setContentsMargins(0, 0, 0, 0)
        self.video_grid.setSpacing(4)
        main_layout.addWidget(self.video_container, stretch=3)

        self.video_widgets = {}
        self.threads = {}
        self.pipelines = {}

        # Pre-initialize UI grid for configured cameras
        cameras = self.config.get("cameras", [{"id": "cam_0", "source": "0"}])
        cols = 2
        for i, cam in enumerate(cameras):
            cam_id = cam["id"]
            vw = VideoWidget()
            vw.setMinimumSize(400, 300)
            self.video_widgets[cam_id] = vw
            
            row = i // cols
            col = i % cols
            self.video_grid.addWidget(vw, row, col)
            
            # Create isolated pipeline per camera
            self.pipelines[cam_id] = Layer1Pipeline(self.config, camera_id=cam_id)
            
        # Layer 5 Initialization (Use first camera's analytics/heatmap)
        first_cam_id = list(self.pipelines.keys())[0]
        self.dashboard_mgr = DashboardManager(self.config, self.pipelines[first_cam_id].storage_mgr.analytics)
        self.dashboard_window = DashboardWindow(
            self.dashboard_mgr, 
            self.pipelines[first_cam_id].scene_mgr.heatmap, 
            self.config
        )

        # ── Right: Controls Panel ─────────────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(360)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        panel = QWidget()
        panel.setStyleSheet("background: #1a1a1a; border-radius: 8px; padding: 8px;")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)

        title = QLabel("AI Dashboard")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        panel_layout.addWidget(title)

        # Sources
        btn_webcam = QPushButton("📷  Start Webcam")
        btn_add_cam = QPushButton("➕  Add Network Camera")
        btn_file   = QPushButton("📂  Open Video File")
        btn_stop   = QPushButton("⏹  Stop")
        btn_dashboard = QPushButton("📊  Open Analytics Dashboard")
        btn_dashboard.setStyleSheet("QPushButton { background: #1976D2; color: white; border: none; border-radius: 6px; padding: 10px; font-weight: bold; font-size: 14px; } QPushButton:hover { background: #1565C0; }")
        
        for btn in [btn_webcam, btn_add_cam, btn_file, btn_stop]:
            btn.setStyleSheet("QPushButton { background: #2a2a2a; border: 1px solid #444; border-radius: 6px; padding: 8px; font-size: 13px; } QPushButton:hover { background: #333; }")
            panel_layout.addWidget(btn)
            
        panel_layout.addWidget(btn_dashboard)

        btn_webcam.clicked.connect(lambda: self._start())
        btn_add_cam.clicked.connect(self._add_camera_dialog)
        btn_file.clicked.connect(self._open_file)
        btn_stop.clicked.connect(self._stop)
        btn_dashboard.clicked.connect(self.dashboard_window.showNormal)

        # Detection Controls
        l1_group = QGroupBox("Detection")
        l1_layout = QVBoxLayout()
        self.chk_pose   = QCheckBox("Pose Estimation")
        self.chk_blur   = QCheckBox("Privacy Blur")
        self.chk_action = QCheckBox("Action Labels")
        
        self.chk_pose.toggled.connect(self._toggle_pose)
        self.chk_blur.toggled.connect(self._toggle_blur)
        self.chk_action.toggled.connect(self._toggle_action)
        
        for chk in [self.chk_pose, self.chk_blur, self.chk_action]:
            l1_layout.addWidget(chk)
        l1_group.setLayout(l1_layout)
        panel_layout.addWidget(l1_group)

        # Scene Intelligence Controls
        l2_group = QGroupBox("Scene Intelligence")
        l2_layout = QVBoxLayout()
        
        self.chk_heatmap = QCheckBox("Show Heatmap")
        self.chk_heatmap.toggled.connect(self._toggle_heatmap)
        l2_layout.addWidget(self.chk_heatmap)
        
        self.chk_zones = QCheckBox("Show Zones")
        self.chk_zones.setChecked(True)
        self.chk_zones.toggled.connect(self._toggle_zones)
        l2_layout.addWidget(self.chk_zones)

        btn_clear = QPushButton("Clear All Zones & Lines")
        btn_clear.clicked.connect(self._clear_all)
        l2_layout.addWidget(btn_clear)
        
        l2_group.setLayout(l2_layout)
        panel_layout.addWidget(l2_group)

        # Zone Editor
        self.zone_editor = ZoneEditor()
        panel_layout.addWidget(self.zone_editor)

        # Tab Widget for Panels
        from PyQt6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(350)  # Prevent squishing of Alert Settings
        
        # Storage & Analytics Panel (Uses first camera for global views)
        self.storage_panel = StoragePanel(
            self.pipelines[first_cam_id].storage_mgr.analytics, 
            self.pipelines[first_cam_id].storage_mgr.clip_storage
        )
        self.tabs.addTab(self.storage_panel, "Storage")
        
        # Initialize Notification Manager
        self.notification_mgr = NotificationManager(
            self.config, 
            QApplication.instance(), 
            self.showNormal
        )
        
        # Alert Settings Panel
        self.alert_panel = AlertSettingsPanel(
            "config/config.yaml",
            self.notification_mgr
        )
        self.tabs.addTab(self.alert_panel, "Alerts (L4)")
        
        panel_layout.addWidget(self.tabs)
        
        # Connect editor signals (Using first camera for drawing)
        first_cam_id = list(self.video_widgets.keys())[0]
        self.video_widgets[first_cam_id].click_event.connect(self.zone_editor.handle_click)
        
        # Broadcast zone creations to all pipelines
        self.zone_editor.zone_created.connect(self._add_zone_to_all)
        self.zone_editor.line_created.connect(self._add_line_to_all)

        panel_layout.addStretch()
        
        scroll_area.setWidget(panel)
        main_layout.addWidget(scroll_area)

        self.status = QStatusBar()
        self.status.setStyleSheet("background: #1a1a1a; color: #888;")
        self.setStatusBar(self.status)

    def _toggle_pose(self, state):
        for p in self.pipelines.values(): p.toggle_pose(state)

    def _toggle_blur(self, state):
        for p in self.pipelines.values(): p.toggle_blur(state)

    def _toggle_action(self, state):
        for p in self.pipelines.values(): p.visualizer.show_action = state

    def _toggle_heatmap(self, state):
        for p in self.pipelines.values(): p.scene_mgr.show_heatmap = state

    def _toggle_zones(self, state):
        for p in self.pipelines.values(): p.scene_mgr.show_zones = state

    def _add_zone_to_all(self, zone):
        for p in self.pipelines.values():
            p.scene_mgr.add_zone(zone)
            
    def _add_line_to_all(self, line):
        for p in self.pipelines.values():
            p.scene_mgr.add_line(line)

    def _clear_all(self):
        for p in self.pipelines.values():
            p.scene_mgr.clear_zones()
            p.scene_mgr.clear_lines()
        self.status.showMessage("All zones and lines cleared.", 3000)

    def _start(self, source=None):
        self._stop()
        logger.info(f"Starting all configured camera streams...")
        
        cameras = self.config.get("cameras", [{"id": "cam_0", "source": 0}])
        cols = 2
        
        for i, cam in enumerate(cameras):
            cam_id = cam["id"]
            cam_src = cam["source"]
            vw = self.video_widgets[cam_id]
            
            if source is not None:
                # Video Mode: Span full grid, hide others
                if cam_id == cameras[0]["id"]:
                    cam_src = source
                    vw.show()
                    self.video_grid.removeWidget(vw)
                    self.video_grid.addWidget(vw, 0, 0, 2, 2)
                else:
                    vw.hide()
                    continue
            else:
                # Webcam Mode: Standard grid
                vw.show()
                row = i // cols
                col = i % cols
                self.video_grid.removeWidget(vw)
                self.video_grid.addWidget(vw, row, col, 1, 1)
                
            thread = PipelineThread(self.pipelines[cam_id], cam_src, camera_id=cam_id)
            
            # Connect signals
            thread.frame_ready.connect(self.video_widgets[cam_id].update_frame)
            if cam_id == cameras[0]["id"]:
                thread.frame_ready.connect(self.dashboard_window.update_heatmap_frame)
                
            thread.stats_ready.connect(self._update_stats)
            thread.alert_ready.connect(self._handle_alert)
            
            if self.notification_mgr:
                thread.saved_alerts_ready.connect(self.notification_mgr.process_alerts)
            
            thread.layer5_metrics_ready.connect(
                lambda m: self.dashboard_mgr.update_metrics(**m)
            )
            
            self.threads[cam_id] = thread
            thread.start()

    def _add_camera_dialog(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        import yaml
        
        url, ok = QInputDialog.getText(self, "Add Network Camera", "Enter RTSP URL, IP Camera Address, or USB Index (e.g. 1):")
        if ok and url:
            source = url.strip()
            # If user types a number like "1", convert it to string '1' for config, but in python we keep string, it's fine.
            
            cameras = self.config.get("cameras", [])
            new_id = f"cam_{len(cameras)}"
            cameras.append({"id": new_id, "source": source})
            self.config["cameras"] = cameras
            
            # Save to config.yaml
            config_path = Path("config/config.yaml")
            try:
                with open(config_path, "w") as f:
                    yaml.dump(self.config, f)
                logger.info(f"Saved new camera {new_id} ({source}) to config.yaml")
            except Exception as e:
                logger.error(f"Failed to save new camera config: {e}")
                QMessageBox.warning(self, "Error", "Failed to save configuration.")
                return
                
            # Initialize pipeline and widget for the new camera dynamically
            vw = VideoWidget()
            vw.setMinimumSize(400, 300)
            self.video_widgets[new_id] = vw
            
            # Create isolated pipeline
            self.pipelines[new_id] = Layer1Pipeline(self.config, camera_id=new_id)
            
            # Restart streams to apply new grid and thread
            self._start()

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.avi)")
        if path:
            self._start(path)
            self.chk_heatmap.setChecked(True)
            from layer2.zone_intrusion import Zone
            hw_zone = Zone(name="Highway Trap", points=[(300, 400), (1600, 400), (1600, 900), (300, 900)])
            self._add_zone_to_all(hw_zone)

    def _stop(self):
        for t in self.threads.values():
            t.stop()
        self.threads.clear()
        self.status.showMessage("All streams stopped")

    def _update_stats(self, fps, count, cam_id):
        self.status.showMessage(f"🟢 Running | {cam_id} | FPS: {fps:.1f} | Objects: {count}")

    def _handle_alert(self, msg):
        self.status.showMessage(msg, 4000)

    def closeEvent(self, event):
        self._stop()
        if self.notification_mgr:
            self.notification_mgr.shutdown()
        event.accept()

if __name__ == "__main__":
    from PyQt6.QtGui import QPalette, QColor
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Native Dark Mode Palette (No layout/clipping bugs)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(18, 18, 18))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(18, 18, 18))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    
    app.setPalette(palette)

    window = MainWindow()
    window.setWindowTitle("Visionguard")
    window.resize(1280, 720)  # Replaced setMinimumSize with a responsive default size
    window.show()
    sys.exit(app.exec())
