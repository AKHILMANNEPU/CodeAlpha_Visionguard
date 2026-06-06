import logging
from typing import List, Optional, Callable
from PyQt6.QtWidgets import QApplication

from .rules_engine import AlertRulesEngine
from .telegram_notifier import TelegramNotifier
from .email_notifier import EmailNotifier
from .sms_notifier import SMSNotifier
from .tray_notifier import TrayNotifier
from .webhook_dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Master controller for Layer 4.
    Takes alerts from Layer 3, evaluates them against Rules,
    and dispatches them to the configured channels.
    """

    def __init__(self, config: dict, app: Optional[QApplication] = None, on_show_app: Optional[Callable] = None):
        self.config = config
        
        # Initialize Rules Engine
        self.rules_engine = AlertRulesEngine(config)
        
        # Initialize Notifiers
        self.telegram = TelegramNotifier(config)
        self.email    = EmailNotifier(config)
        self.sms      = SMSNotifier(config)
        self.webhook  = WebhookDispatcher(config)
        
        # Tray notifier requires the PyQt application
        if app:
            self.tray = TrayNotifier(config, app, on_show_callback=on_show_app)
        else:
            self.tray = None
            logger.warning("NotificationManager initialized without QApplication. Tray notifications disabled.")

        logger.info("Notification Manager initialized with all channels.")

    def process_alerts(self, alert_records: List[dict], raw_alerts: List[str] = None):
        """
        Process a batch of saved alerts from Layer 3.
        1. Evaluate rules to see who gets what.
        2. Dispatch to channels asynchronously.
        """
        if not alert_records:
            return
            
        raw = raw_alerts or []
        
        # 1. Route alerts using rules engine
        routed_notifications = self.rules_engine.evaluate(alert_records, raw)
        
        # 2. Dispatch to active channels
        for notif in routed_notifications:
            channels = notif.get("channels", [])
            
            if "telegram" in channels and self.telegram.enabled:
                self.telegram.send(notif)
                
            if "email" in channels and self.email.enabled:
                self.email.send(notif)
                
            if "sms" in channels and self.sms.enabled:
                self.sms.send(notif)
                
            if "webhook" in channels and self.webhook.enabled:
                self.webhook.send(notif)
                
            if "tray" in channels and self.tray and self.tray.enabled:
                self.tray.send(notif)

    def shutdown(self):
        """Clean up resources on app exit."""
        if self.tray:
            self.tray.hide()
        logger.info("Notification Manager shutdown.")
