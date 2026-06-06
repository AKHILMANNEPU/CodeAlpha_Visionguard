import smtplib
import threading
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.image     import MIMEImage
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime
from typing               import List, Optional

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Sends email alerts via SMTP.
    Works with Gmail, Outlook, Yahoo, or any SMTP server.

    Gmail setup (free):
    1. Enable 2-Factor Authentication on your Gmail account
    2. Go to Google Account → Security → App Passwords
    3. Create an App Password for "Mail"
    4. Use that 16-char password (not your real password) below

    Sends:
    - HTML email with formatted alert details
    - Inline snapshot image (if available)
    - All sends are async — never blocks pipeline
    """

    def __init__(self, config: dict):
        cfg              = config.get("email", {})
        self.smtp_host   = cfg.get("smtp_host",   "smtp.gmail.com")
        self.smtp_port   = cfg.get("smtp_port",   587)
        self.sender      = cfg.get("sender",      "")
        self.password    = cfg.get("password",    "")
        self.recipients  = cfg.get("recipients",  [])
        self.enabled     = cfg.get("enabled",     False)
        self.use_tls     = cfg.get("use_tls",     True)
        self.send_min_priority = cfg.get("send_min_priority", "HIGH")
        self._priority_levels  = {"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}

        if self.enabled and (not self.sender or not self.password):
            logger.warning("Email enabled but sender/password missing.")
            self.enabled = False

    def send(self, notification: dict):
        """Send email in background thread."""
        if not self.enabled or not self.recipients:
            return

        # Check minimum priority threshold
        notif_level = self._priority_levels.get(
            notification.get("priority", "LOW"), 1
        )
        min_level   = self._priority_levels.get(self.send_min_priority, 3)
        if notif_level < min_level:
            return

        thread = threading.Thread(
            target=self._send_email,
            args=(notification,),
            daemon=True
        )
        thread.start()

    def _send_email(self, notification: dict):
        """Build and send HTML email with optional snapshot attachment."""
        try:
            msg = MIMEMultipart("related")
            priority   = notification.get("priority",   "MEDIUM")
            alert_type = notification.get("alert_type", "ALERT")
            message    = notification.get("message",    "")
            snapshot   = notification.get("snapshot_path", "")
            timestamp  = notification.get("timestamp",  datetime.now().isoformat())
            zone       = notification.get("zone_name",  "N/A")
            track_id   = notification.get("track_id",   "N/A")
            class_name = notification.get("class_name", "N/A")

            # Email subject
            priority_prefix = {
                "LOW":"[INFO]","MEDIUM":"[WARNING]",
                "HIGH":"[ALERT]","CRITICAL":"[CRITICAL]"
            }.get(priority, "[ALERT]")
            msg["Subject"] = (f"{priority_prefix} {alert_type.replace('_',' ')} "
                              f"— {zone} @ {timestamp[:16]}")
            msg["From"]    = self.sender
            msg["To"]      = ", ".join(self.recipients)

            # HTML body
            color_map = {
                "LOW":"#2196F3","MEDIUM":"#FF9800",
                "HIGH":"#F44336","CRITICAL":"#9C27B0"
            }
            bar_color = color_map.get(priority, "#F44336")

            has_image = snapshot and os.path.exists(snapshot)
            image_html = '<img src="cid:snapshot" style="max-width:600px;border-radius:4px;" />' \
                         if has_image else ""

            html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
  <div style="max-width:600px;margin:0 auto;background:#fff;
              border-radius:8px;overflow:hidden;
              box-shadow:0 2px 8px rgba(0,0,0,0.15);">

    <div style="background:{bar_color};padding:20px 24px;">
      <h2 style="color:#fff;margin:0;font-size:20px;">
        {alert_type.replace('_',' ')} — {priority}
      </h2>
      <p style="color:rgba(255,255,255,0.85);margin:4px 0 0;">
        {timestamp}
      </p>
    </div>

    <div style="padding:24px;">
      <table style="width:100%;border-collapse:collapse;">
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#666;width:140px;">Alert Type</td>
          <td style="padding:10px 0;font-weight:600;">
            {alert_type.replace('_',' ')}
          </td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#666;">Priority</td>
          <td style="padding:10px 0;">
            <span style="background:{bar_color};color:#fff;
                         padding:2px 10px;border-radius:12px;font-size:13px;">
              {priority}
            </span>
          </td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#666;">Object Class</td>
          <td style="padding:10px 0;">{class_name}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#666;">Track ID</td>
          <td style="padding:10px 0;">#{track_id}</td>
        </tr>
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:10px 0;color:#666;">Zone</td>
          <td style="padding:10px 0;">{zone}</td>
        </tr>
        <tr>
          <td style="padding:10px 0;color:#666;">Full Message</td>
          <td style="padding:10px 0;font-size:13px;color:#444;">
            {message}
          </td>
        </tr>
      </table>

      {"<h3 style='margin-top:24px;color:#333;'>Snapshot</h3>" + image_html
       if has_image else ""}
    </div>

    <div style="background:#f9f9f9;padding:14px 24px;
                border-top:1px solid #eee;font-size:12px;color:#999;">
      Automated alert from Intelligent Surveillance System
    </div>
  </div>
</body>
</html>"""

            # Attach HTML
            msg.attach(MIMEText(html, "html"))

            # Attach inline snapshot image
            if has_image:
                with open(snapshot, "rb") as img_file:
                    img = MIMEImage(img_file.read())
                    img.add_header("Content-ID", "<snapshot>")
                    img.add_header(
                        "Content-Disposition", "inline",
                        filename=os.path.basename(snapshot)
                    )
                    msg.attach(img)

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(
                    self.sender,
                    self.recipients,
                    msg.as_string()
                )
            logger.info(
                f"Email sent to {self.recipients}: [{priority}] {alert_type}"
            )

        except smtplib.SMTPAuthenticationError:
            logger.error("Email auth failed. Check sender/password in config.")
        except Exception as e:
            logger.error(f"Email send error: {e}")

    def test_connection(self) -> bool:
        """Test SMTP connection and send a test email."""
        if not self.enabled:
            return False
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.sender, self.password)
                test_msg = MIMEText(
                    "✅ Surveillance system email connection test — OK"
                )
                test_msg["Subject"] = "[TEST] Surveillance System Alert"
                test_msg["From"]    = self.sender
                test_msg["To"]      = ", ".join(self.recipients)
                server.sendmail(self.sender, self.recipients, test_msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email test failed: {e}")
            return False
