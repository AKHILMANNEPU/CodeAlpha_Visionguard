import re
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """
    A single routing rule that maps alert conditions to notification channels.

    Logic:
        IF alert_type in match_types
        AND class_name in match_classes (optional)
        AND zone_name matches zone_pattern (optional)
        AND current time in active_hours (optional)
        AND cooldown not active
        THEN send to channels with given priority

    Examples:
        Rule: "Night Zone Entry"
            match_types   = ["ZONE_ENTRY"]
            match_classes = ["person"]
            active_hours  = (22, 6)          # 10PM to 6AM
            channels      = ["telegram", "sms"]
            priority      = "HIGH"
            cooldown      = 120

        Rule: "All Crowd Alerts"
            match_types   = ["CROWD_HIGH"]
            channels      = ["email", "webhook"]
            priority      = "MEDIUM"
            cooldown      = 300
    """
    name          : str
    match_types   : List[str]             # alert types to match, ["all"] = all
    channels      : List[str]             # ["telegram","email","tray","sms","webhook"]
    priority      : str         = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    match_classes : List[str]   = field(default_factory=lambda: ["all"])
    zone_pattern  : Optional[str] = None  # regex pattern on zone name
    active_hours  : Optional[tuple] = None  # (start_hour, end_hour) 24h format
    cooldown_sec  : int         = 60      # minimum seconds between same alert
    enabled       : bool        = True


# Priority → numeric for comparison
PRIORITY_LEVEL = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# Alert type → readable label
ALERT_LABELS = {
    "ZONE_ENTRY"  : "Zone Intrusion",
    "ZONE_EXIT"   : "Zone Exit",
    "LINE_CROSS"  : "Line Crossed",
    "CROWD_HIGH"  : "Crowd Alert",
    "DWELL"       : "Loitering Detected",
    "FALLING"     : "Fall Detected",
    "LOITERING"   : "Loitering",
    "GENERAL"     : "Detection Alert"
}


class AlertRulesEngine:
    """
    Evaluates each incoming alert against all defined rules.
    Determines WHICH channels to notify and at WHAT priority.

    Key features:
    - Cooldown per (alert_type, zone_name) — prevents spam
    - Time-of-day filtering — different rules for day vs night
    - Class-based filtering — only alert on persons, not cars
    - Priority scoring — aggregate priority across matched rules
    - Deduplication — same alert doesn't fire twice in one frame
    """

    def __init__(self, config: dict):
        cfg         = config.get("notifications", {})
        self.rules  : List[AlertRule] = []
        self._cooldowns: Dict[str, float] = {}  # key→last_fire_time
        self._fired_this_frame: Set[str] = set()

        # Load rules from config
        self._load_rules(cfg.get("rules", []))

        # Add default rules if none configured
        if not self.rules:
            self._add_default_rules(cfg)

        logger.info(f"Rules engine ready: {len(self.rules)} rules loaded.")

    def _load_rules(self, rules_cfg: list):
        for r in rules_cfg:
            self.rules.append(AlertRule(
                name         = r.get("name", "Rule"),
                match_types  = r.get("match_types", ["all"]),
                channels     = r.get("channels", ["tray"]),
                priority     = r.get("priority", "MEDIUM"),
                match_classes= r.get("match_classes", ["all"]),
                zone_pattern = r.get("zone_pattern", None),
                active_hours = tuple(r["active_hours"]) if r.get("active_hours") else None,
                cooldown_sec = r.get("cooldown_sec", 60),
                enabled      = r.get("enabled", True)
            ))

    def _add_default_rules(self, cfg: dict):
        """Sensible defaults when no rules are defined in config."""
        default_channels = cfg.get("default_channels", ["tray"])

        self.rules.extend([
            AlertRule(
                name        = "Zone Intrusion",
                match_types = ["ZONE_ENTRY"],
                channels    = default_channels,
                priority    = "HIGH",
                cooldown_sec= 30
            ),
            AlertRule(
                name        = "Fall Detection",
                match_types = ["FALLING"],
                channels    = default_channels + ["telegram"]
                              if "telegram" not in default_channels else default_channels,
                priority    = "CRITICAL",
                cooldown_sec= 10
            ),
            AlertRule(
                name        = "Crowd Alert",
                match_types = ["CROWD_HIGH"],
                channels    = default_channels,
                priority    = "HIGH",
                cooldown_sec= 120
            ),
            AlertRule(
                name        = "Dwell / Loitering",
                match_types = ["DWELL", "LOITERING"],
                channels    = default_channels,
                priority    = "MEDIUM",
                cooldown_sec= 60
            ),
            AlertRule(
                name        = "Line Crossing",
                match_types = ["LINE_CROSS"],
                channels    = ["tray"],
                priority    = "LOW",
                cooldown_sec= 5
            ),
        ])

    def evaluate(
        self,
        alert_records: list,    # from Layer 3 EventLog
        raw_alerts   : list     # raw strings from Layer 2
    ) -> List[dict]:
        """
        Evaluate all alert records against all rules.

        Returns list of routed notification dicts:
        [
          {
            "message"     : str,
            "alert_type"  : str,
            "priority"    : str,
            "channels"    : ["telegram", "email", ...],
            "track_id"    : int or None,
            "zone_name"   : str or None,
            "class_name"  : str or None,
            "snapshot_path": str,
            "clip_path"   : str,
            "label"       : str   (human readable type)
          }
        ]
        """
        routed     = []
        now        = time.time()
        current_hr = datetime.now().hour
        self._fired_this_frame.clear()

        for record in alert_records:
            alert_type  = record.get("type",       "GENERAL")
            track_id    = record.get("track_id",   None)
            zone_name   = record.get("zone_name",  "")
            class_name  = record.get("class_name", "unknown")
            message     = record.get("message",    "")
            snapshot    = record.get("snapshot_path", "")
            clip        = record.get("clip_path",     "")

            # Deduplicate within same frame
            dedup_key = f"{alert_type}_{zone_name}_{track_id}"
            if dedup_key in self._fired_this_frame:
                continue

            matched_channels : Set[str] = set()
            matched_priority : str      = "LOW"

            for rule in self.rules:
                if not rule.enabled:
                    continue

                # Match alert type
                if "all" not in rule.match_types and \
                   alert_type not in rule.match_types:
                    continue

                # Match class
                if "all" not in rule.match_classes and \
                   class_name not in rule.match_classes:
                    continue

                # Match zone pattern
                if rule.zone_pattern and zone_name:
                    if not re.search(rule.zone_pattern, zone_name, re.IGNORECASE):
                        continue

                # Time of day filter
                if rule.active_hours:
                    start_h, end_h = rule.active_hours
                    if start_h <= end_h:
                        if not (start_h <= current_hr < end_h):
                            continue
                    else:  # wraps midnight e.g. (22, 6)
                        if not (current_hr >= start_h or current_hr < end_h):
                            continue

                # Cooldown check
                cooldown_key = f"{rule.name}_{alert_type}_{zone_name}"
                last_fired   = self._cooldowns.get(cooldown_key, 0)
                if now - last_fired < rule.cooldown_sec:
                    continue

                # Rule matched — collect channels + priority
                matched_channels.update(rule.channels)
                if PRIORITY_LEVEL.get(rule.priority, 0) > \
                   PRIORITY_LEVEL.get(matched_priority, 0):
                    matched_priority = rule.priority

                self._cooldowns[cooldown_key] = now

            if matched_channels:
                self._fired_this_frame.add(dedup_key)
                routed.append({
                    "message"      : message,
                    "alert_type"   : alert_type,
                    "priority"     : matched_priority,
                    "channels"     : list(matched_channels),
                    "track_id"     : track_id,
                    "zone_name"    : zone_name,
                    "class_name"   : class_name,
                    "snapshot_path": snapshot,
                    "clip_path"    : clip,
                    "label"        : ALERT_LABELS.get(alert_type, alert_type),
                    "timestamp"    : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        return routed

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)
        logger.info(f"Rule added: '{rule.name}'")

    def remove_rule(self, name: str):
        self.rules = [r for r in self.rules if r.name != name]

    def get_rules(self) -> List[AlertRule]:
        return list(self.rules)
