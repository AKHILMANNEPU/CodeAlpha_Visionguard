import json
import threading
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """
    Sends HTTP POST notifications to external webhooks.

    Supports:
    - Slack Incoming Webhooks (free)
    - Microsoft Teams Incoming Webhooks (free)
    - Discord Webhooks (free)
    - Custom HTTP endpoints (any URL)

    Slack setup (free):
    1. Go to api.slack.com/apps → Create New App
    2. Enable Incoming Webhooks
    3. Add to Workspace → Select Channel
    4. Copy Webhook URL → paste in config

    Teams setup (free):
    1. In Teams channel → Connectors → Incoming Webhook
    2. Configure → name + icon → copy URL

    Discord setup (free):
    1. Channel settings → Integrations → Webhooks
    2. New Webhook → Copy URL

    All sends are async — never blocks pipeline.
    Includes retry logic for network failures.
    """

    def __init__(self, config: dict):
        cfg           = config.get("webhook", {})
        self.endpoints: List[Dict] = cfg.get("endpoints", [])
        self.enabled  = cfg.get("enabled", False) and bool(self.endpoints)
        self.timeout  = cfg.get("timeout_seconds", 10)
        self.retries  = cfg.get("retries", 2)

        if self.enabled:
            logger.info(f"Webhook dispatcher ready: {len(self.endpoints)} endpoints")
        else:
            logger.info("Webhook dispatcher disabled.")

    def send(self, notification: dict):
        """Dispatch to all configured endpoints in background threads."""
        if not self.enabled:
            return

        for endpoint in self.endpoints:
            if not endpoint.get("enabled", True):
                continue
            thread = threading.Thread(
                target=self._dispatch,
                args=(notification, endpoint),
                daemon=True
            )
            thread.start()

    def _dispatch(self, notification: dict, endpoint: dict):
        """Build and POST to a single endpoint. Retries on failure."""
        import requests

        url        = endpoint.get("url", "")
        fmt        = endpoint.get("format", "generic")  # slack, teams, discord, generic
        min_prio   = endpoint.get("min_priority", "LOW")

        # Priority filter
        priority_levels = {"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}
        notif_level = priority_levels.get(notification.get("priority","LOW"), 1)
        min_level   = priority_levels.get(min_prio, 1)
        if notif_level < min_level:
            return

        payload = self._build_payload(notification, fmt)
        headers = {"Content-Type": "application/json"}

        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(
                    url, json=payload, headers=headers,
                    timeout=self.timeout
                )
                if resp.status_code in (200, 204):
                    logger.info(
                        f"Webhook [{fmt}] sent: "
                        f"{notification.get('alert_type')} → {url[:40]}"
                    )
                    return
                else:
                    logger.warning(
                        f"Webhook [{fmt}] HTTP {resp.status_code}: {url[:40]}"
                    )
            except Exception as e:
                if attempt < self.retries:
                    time.sleep(2 ** attempt)   # exponential backoff
                else:
                    logger.error(f"Webhook [{fmt}] failed after retries: {e}")

    def _build_payload(self, notification: dict, fmt: str) -> dict:
        """Build platform-specific payload format."""
        priority   = notification.get("priority",   "MEDIUM")
        alert_type = notification.get("alert_type", "ALERT")
        message    = notification.get("message",    "")
        zone       = notification.get("zone_name",  "N/A")
        class_name = notification.get("class_name", "N/A")
        timestamp  = notification.get("timestamp",  "")
        track_id   = notification.get("track_id",   "N/A")

        colors = {
            "LOW":"#2196F3","MEDIUM":"#FF9800",
            "HIGH":"#F44336","CRITICAL":"#9C27B0"
        }
        color = colors.get(priority, "#F44336")
        emoji = {"LOW":"ℹ️","MEDIUM":"⚠️","HIGH":"🚨","CRITICAL":"🆘"}.get(
            priority,"⚠️"
        )

        if fmt == "slack":
            return {
                "attachments": [{
                    "color"   : color,
                    "title"   : f"{emoji} {alert_type.replace('_',' ')} — {priority}",
                    "text"    : message,
                    "fields"  : [
                        {"title":"Class",     "value":class_name, "short":True},
                        {"title":"Track ID",  "value":f"#{track_id}","short":True},
                        {"title":"Zone",      "value":zone,       "short":True},
                        {"title":"Time",      "value":timestamp,  "short":True},
                    ],
                    "footer"  : "Surveillance System",
                    "ts"      : int(time.time())
                }]
            }

        elif fmt == "teams":
            return {
                "@type"      : "MessageCard",
                "@context"   : "https://schema.org/extensions",
                "themeColor" : color.lstrip("#"),
                "summary"    : f"{alert_type} Alert",
                "sections"   : [{
                    "activityTitle"   : f"{emoji} {alert_type.replace('_',' ')}",
                    "activitySubtitle": timestamp,
                    "facts"           : [
                        {"name":"Priority",  "value":priority},
                        {"name":"Class",     "value":class_name},
                        {"name":"Track ID",  "value":f"#{track_id}"},
                        {"name":"Zone",      "value":zone},
                        {"name":"Message",   "value":message[:200]}
                    ]
                }]
            }

        elif fmt == "discord":
            return {
                "embeds": [{
                    "title"      : f"{emoji} {alert_type.replace('_',' ')}",
                    "description": message,
                    "color"      : int(color.lstrip("#"), 16),
                    "fields"     : [
                        {"name":"Class",     "value":class_name, "inline":True},
                        {"name":"Track ID",  "value":f"#{track_id}","inline":True},
                        {"name":"Zone",      "value":zone,       "inline":True},
                    ],
                    "footer"     : {"text": "Surveillance System"},
                    "timestamp"  : datetime.utcnow().isoformat()
                }]
            }

        else:  # generic JSON
            return {
                "alert_type" : alert_type,
                "priority"   : priority,
                "message"    : message,
                "class_name" : class_name,
                "track_id"   : track_id,
                "zone_name"  : zone,
                "timestamp"  : timestamp
            }
