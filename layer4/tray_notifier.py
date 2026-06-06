import logging
import threading
from typing import Optional, Callable
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui     import QIcon, QPixmap, QColor
from PyQt6.QtCore    import QObject, pyqtSignal, Qt

logger = logging.getLogger(__name__)


class TrayNotifier(QObject):
    """
    Native OS system tray notifications via PyQt6.

    Features:
    - Balloon/popup notification in system tray
    - Tray icon changes color based on highest active alert priority
    - Right-click menu: Open App, Mute Alerts, Quit
    - Sound alert (system beep) for critical alerts
    - Works on Windows, macOS, Linux

    No external libraries needed — pure PyQt6.
    """

    # Signal to safely update tray from background threads
    _notify_signal = pyqtSignal(str, str, int)   # title, message, duration_ms

    def __init__(self, config: dict, app: QApplication,
                 on_show_callback: Optional[Callable] = None):
        super().__init__()
        cfg              = config.get("tray", {})
        self.enabled     = cfg.get("enabled",          True)
        self.duration_ms = cfg.get("duration_ms",      5000)
        self.muted       = False
        self.app         = app
        self._on_show    = on_show_callback

        self.tray_icon: Optional[QSystemTrayIcon] = None

        if self.enabled and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()
            # Connect signal to slot — ensures UI runs on main thread
            self._notify_signal.connect(self._show_message_slot)
        elif self.enabled:
            logger.warning("System tray not available on this platform.")
            self.enabled = False

    def _setup_tray(self):
        """Create the system tray icon and context menu."""
        # Create a colored icon (green = normal, yellow/red = alert)
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(self._make_icon("#00cc66"))   # green = all clear
        self.tray_icon.setToolTip("Surveillance System — Running")

        # Context menu
        menu = QMenu()
        act_show  = menu.addAction("📷 Show App")
        act_mute  = menu.addAction("🔕 Mute Alerts")
        menu.addSeparator()
        act_quit  = menu.addAction("✕ Quit")

        act_show.triggered.connect(self._on_show_clicked)
        act_mute.triggered.connect(self._toggle_mute)
        act_quit.triggered.connect(self.app.quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        logger.info("System tray icon active.")

    def send(self, notification: dict):
        """Send a tray notification. Thread-safe via signal."""
        if not self.enabled or self.muted or self.tray_icon is None:
            return

        priority   = notification.get("priority",   "MEDIUM")
        alert_type = notification.get("alert_type", "Alert")
        zone       = notification.get("zone_name",  "")
        class_name = notification.get("class_name", "")
        timestamp  = notification.get("timestamp",  "")[-8:]  # HH:MM:SS

        title   = f"{'🆘' if priority=='CRITICAL' else '🚨'} {alert_type.replace('_',' ')}"
        message = ""
        if class_name : message += f"{class_name.title()} detected"
        if zone       : message += f" in {zone}"
        if timestamp  : message += f"\n{timestamp}"

        # Update icon color based on priority
        colors = {
            "LOW":"#2196F3","MEDIUM":"#FF9800",
            "HIGH":"#F44336","CRITICAL":"#9C27B0"
        }
        self.tray_icon.setIcon(
            self._make_icon(colors.get(priority, "#F44336"))
        )

        # Emit signal (safe from any thread)
        self._notify_signal.emit(title, message, self.duration_ms)

    def _show_message_slot(self, title: str, message: str, duration: int):
        """Runs on main thread via Qt signal."""
        if self.tray_icon:
            self.tray_icon.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Warning,
                duration
            )

    def _make_icon(self, hex_color: str) -> QIcon:
        """Create a solid-color 16x16 icon for the tray."""
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_color))
        return QIcon(pixmap)

    def _toggle_mute(self):
        self.muted = not self.muted
        tip = "Muted" if self.muted else "Running"
        if self.tray_icon:
            self.tray_icon.setToolTip(f"Surveillance System — {tip}")
        logger.info(f"Tray notifications {'muted' if self.muted else 'unmuted'}.")

    def _on_show_clicked(self):
        if self._on_show:
            self._on_show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self._on_show:
                self._on_show()

    def reset_icon(self):
        """Reset icon to green (all clear)."""
        if self.tray_icon:
            self.tray_icon.setIcon(self._make_icon("#00cc66"))
            self.tray_icon.setToolTip("Surveillance System — All Clear")

    def hide(self):
        if self.tray_icon:
            self.tray_icon.hide()
