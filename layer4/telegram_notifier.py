import asyncio
import threading
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends Telegram messages and photos via Bot API.

    Setup (free, 5 minutes):
    1. Open Telegram → search @BotFather
    2. Send /newbot → follow prompts → get BOT_TOKEN
    3. Start a chat with your bot OR add to a group
    4. Get your CHAT_ID:
       → Send any message to your bot
       → Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
       → Find "chat":{"id": <YOUR_CHAT_ID>}

    Cost: completely free — no limits for personal/small use.

    Sends:
    - Text message for LOW/MEDIUM alerts
    - Photo + caption for HIGH/CRITICAL alerts (uses snapshot)
    - All sends are async in background thread — never blocks pipeline
    """

    def __init__(self, config: dict):
        cfg             = config.get("telegram", {})
        self.token      = cfg.get("bot_token",  "")
        self.chat_id    = cfg.get("chat_id",    "")
        self.enabled    = cfg.get("enabled",    False)
        self.send_photos= cfg.get("send_photos", True)
        self.bot        = None

        if self.enabled and self.token and self.chat_id:
            self._init_bot()
        elif self.enabled:
            logger.warning("Telegram enabled but bot_token or chat_id missing.")

    def _init_bot(self):
        try:
            from telegram import Bot
            self.bot = Bot(token=self.token)
            logger.info("Telegram bot initialized.")
        except ImportError:
            logger.error("python-telegram-bot not installed. "
                         "Run: pip install python-telegram-bot==20.7")
            self.enabled = False
        except Exception as e:
            logger.error(f"Telegram init failed: {e}")
            self.enabled = False

    def send(self, notification: dict):
        """
        Send a notification. Runs in background thread.
        Never blocks the calling thread.
        """
        if not self.enabled or self.bot is None:
            return

        thread = threading.Thread(
            target=self._send_async,
            args=(notification,),
            daemon=True
        )
        thread.start()

    def _send_async(self, notification: dict):
        """Called in background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._send_coroutine(notification))
            loop.close()
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def _send_coroutine(self, notification: dict):
        """Async send — photo if available, text otherwise."""
        priority     = notification.get("priority", "MEDIUM")
        alert_type   = notification.get("alert_type", "ALERT")
        message      = notification.get("message",   "")
        snapshot     = notification.get("snapshot_path", "")
        timestamp    = notification.get("timestamp", "")
        zone         = notification.get("zone_name", "")
        track_id     = notification.get("track_id")
        class_name   = notification.get("class_name", "")

        # Priority emoji
        emoji = {"LOW":"ℹ️","MEDIUM":"⚠️","HIGH":"🚨","CRITICAL":"🆘"}.get(
            priority, "⚠️"
        )

        caption = (
            f"{emoji} *{alert_type.replace('_',' ')}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {timestamp}\n"
        )
        if class_name : caption += f"👤 Class: {class_name}\n"
        if track_id   : caption += f"🔢 Track ID: #{track_id}\n"
        if zone       : caption += f"📍 Zone: {zone}\n"
        caption += f"\n`{message[:200]}`"

        try:
            if (self.send_photos and snapshot and
                    os.path.exists(snapshot) and
                    priority in ("HIGH", "CRITICAL")):
                # Send photo with caption
                with open(snapshot, "rb") as photo:
                    await self.bot.send_photo(
                        chat_id   = self.chat_id,
                        photo     = photo,
                        caption   = caption,
                        parse_mode= "Markdown"
                    )
            else:
                # Send text message
                await self.bot.send_message(
                    chat_id    = self.chat_id,
                    text       = caption,
                    parse_mode = "Markdown"
                )
            logger.info(f"Telegram sent: [{priority}] {alert_type}")
        except Exception as e:
            logger.error(f"Telegram API error: {e}")

    def test_connection(self) -> bool:
        """Test Telegram connection — call from settings panel."""
        if not self.enabled or self.bot is None:
            return False
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.bot.send_message(
                chat_id    = self.chat_id,
                text       = "✅ Object Detection System — Test message OK",
                parse_mode = "Markdown"
            ))
            loop.close()
            return True
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            return False
