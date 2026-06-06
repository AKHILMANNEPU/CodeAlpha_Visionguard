import pytest
import smtplib
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from layer4.email_notifier import EmailNotifier
from layer4.notification_manager import NotificationManager

@pytest.fixture
def email_config():
    return {
        "email": {
            "enabled": True,
            "smtp_host": "smtp.test.local",
            "smtp_port": 587,
            "sender": "bot@test.local",
            "password": "fake_password",
            "recipients": ["admin@test.local"],
            "send_min_priority": "LOW"
        }
    }

# =====================================================================
# 6. Email Notification Testing
# =====================================================================

def test_successful_email_delivery(email_config, mocker):
    """TC-NE-016 & TC-NE-017: Email successful delivery & subject validation."""
    # Mock SMTP to prevent actual network calls
    mock_smtp = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)
    # The context manager returns the mock itself
    mock_smtp.__enter__.return_value = mock_smtp
    
    notifier = EmailNotifier(email_config)
    
    notification = {
        "alert_type": "ZONE_ENTRY",
        "message": "Test Message",
        "priority": "HIGH",
        "zone_name": "Front Door"
    }
    
    # We call _send_email directly to test synchronously (send() uses threads)
    notifier._send_email(notification)
    
    # Verify SMTP calls
    mock_smtp.login.assert_called_once_with("bot@test.local", "fake_password")
    mock_smtp.sendmail.assert_called_once()
    
    # Verify Subject in the sent message payload
    args, kwargs = mock_smtp.sendmail.call_args
    sent_msg_string = args[2]
    
    assert "bot@test.local" in sent_msg_string
    assert "admin@test.local" in sent_msg_string
    assert "ZONE_ENTRY" in sent_msg_string

def test_multiple_recipients(email_config, mocker):
    """TC-NE-019: Multiple recipients."""
    email_config["email"]["recipients"] = ["admin1@test.local", "admin2@test.local"]
    
    mock_smtp = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)
    mock_smtp.__enter__.return_value = mock_smtp
    
    notifier = EmailNotifier(email_config)
    notifier._send_email({"alert_type": "TEST"})
    
    args, _ = mock_smtp.sendmail.call_args
    # args[1] is the recipients list
    assert args[1] == ["admin1@test.local", "admin2@test.local"]

# =====================================================================
# 7. SMTP Failure Testing
# =====================================================================

def test_smtp_wrong_password(email_config, mocker, caplog):
    """TC-NE-021: Wrong Password -> Graceful failure."""
    mock_smtp = mocker.MagicMock()
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)
    mock_smtp.__enter__.return_value = mock_smtp
    
    # Make login throw authentication error
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
    
    notifier = EmailNotifier(email_config)
    
    # Should not crash
    notifier._send_email({"alert_type": "TEST"})
    
    assert "Email auth failed" in caplog.text

def test_smtp_server_offline(email_config, mocker, caplog):
    """TC-NE-022: SMTP Server Offline -> Network error handled gracefully."""
    # Patch the class itself to throw exception on instantiation
    mocker.patch("smtplib.SMTP", side_effect=ConnectionRefusedError("Offline"))
    
    notifier = EmailNotifier(email_config)
    notifier._send_email({"alert_type": "TEST"})
    
    assert "Email send error" in caplog.text

# =====================================================================
# 8. Queue Management Testing
# =====================================================================

def test_concurrent_alert_generation_queue(email_config, mocker):
    """TC-NE-029: 16 cameras trigger simultaneously. Manager dispatches them."""
    mgr = NotificationManager({"notifications": {}})
    mgr.email = EmailNotifier(email_config)
    mgr.email.enabled = True
    
    mock_send = mocker.patch.object(mgr.email, "send")
    
    # We bypass rule engine for this test to just push notifications
    notifications = [{"alert_type": "TEST", "channels": ["email"]} for _ in range(16)]
    
    # Manager receives 16 notifications and routes them
    # process_alerts normally does routing, so we mock evaluate
    mocker.patch.object(mgr.rules_engine, "evaluate", return_value=notifications)
    
    mgr.process_alerts([{"some_alert": 1}])
    
    # Should be called 16 times
    assert mock_send.call_count == 16
