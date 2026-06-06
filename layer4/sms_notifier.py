import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SMSNotifier:
    """
    Sends SMS alerts via Twilio.

    Free trial setup:
    1. Sign up at twilio.com (no credit card required for trial)
    2. Get FREE $15 trial credit
    3. Get Account SID, Auth Token, and a free Twilio phone number
    4. Trial only sends to verified numbers — add your number in Twilio console

    Sends only CRITICAL alerts by default (SMS costs money).
    Twilio trial credit: ~150 SMS messages.

    Cost: $0 for trial, ~$0.0075/SMS after that.
    """

    def __init__(self, config: dict):
        cfg              = config.get("sms", {})
        self.account_sid = cfg.get("account_sid", "")
        self.auth_token  = cfg.get("auth_token",  "")
        self.from_number = cfg.get("from_number", "")   # Twilio number
        self.to_numbers  = cfg.get("to_numbers",  [])   # recipient list
        self.enabled     = cfg.get("enabled",     False)
        self.min_priority= cfg.get("min_priority","CRITICAL")  # SMS only critical
        self.client      = None
        self._priority   = {"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}

        if self.enabled:
            self._init_client()

    def _init_client(self):
        try:
            from twilio.rest import Client
            self.client = Client(self.account_sid, self.auth_token)
            logger.info("Twilio SMS client initialized.")
        except ImportError:
            logger.error("twilio not installed. Run: pip install twilio")
            self.enabled = False
        except Exception as e:
            logger.error(f"Twilio init failed: {e}")
            self.enabled = False

    def send(self, notification: dict):
        if not self.enabled or self.client is None:
            return

        # Only send above minimum priority threshold
        notif_level = self._priority.get(
            notification.get("priority","LOW"), 1
        )
        min_level   = self._priority.get(self.min_priority, 4)
        if notif_level < min_level:
            return

        thread = threading.Thread(
            target=self._send_sms,
            args=(notification,),
            daemon=True
        )
        thread.start()

    def _send_sms(self, notification: dict):
        priority   = notification.get("priority",   "CRITICAL")
        alert_type = notification.get("alert_type", "ALERT")
        zone       = notification.get("zone_name",  "")
        class_name = notification.get("class_name", "")
        timestamp  = notification.get("timestamp",  "")[:16]

        body = (
            f"[{priority}] SURVEILLANCE ALERT\n"
            f"Type: {alert_type.replace('_',' ')}\n"
        )
        if class_name : body += f"Object: {class_name}\n"
        if zone       : body += f"Zone: {zone}\n"
        body += f"Time: {timestamp}"

        for number in self.to_numbers:
            try:
                self.client.messages.create(
                    body=body,
                    from_=self.from_number,
                    to=number
                )
                logger.info(f"SMS sent to {number}: [{priority}] {alert_type}")
            except Exception as e:
                logger.error(f"SMS to {number} failed: {e}")
