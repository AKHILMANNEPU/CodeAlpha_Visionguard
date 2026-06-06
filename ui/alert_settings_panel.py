from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, 
    QLabel, QPushButton, QHBoxLayout, QMessageBox,
    QFormLayout, QLineEdit
)
from PyQt6.QtCore import Qt
import yaml
import logging

logger = logging.getLogger(__name__)

class AlertSettingsPanel(QWidget):
    """
    Settings panel for configuring Layer 4 notifications (Telegram, Email, etc).
    Updates config.yaml dynamically.
    """
    
    def __init__(self, config_path: str, notification_manager=None):
        super().__init__()
        self.config_path = config_path
        self.notification_manager = notification_manager
        
        # Load current config
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a scroll area
        from PyQt6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        # Container widget inside scroll area
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        title = QLabel("Layer 4: Alert Notifications")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #aaa;")
        layout.addWidget(title)

        # 1. System Tray
        tray_group = QGroupBox("System Tray Popups")
        tray_layout = QVBoxLayout()
        self.cb_tray = QCheckBox("Enable System Tray Notifications")
        self.cb_tray.setChecked(self.config.get('tray', {}).get('enabled', True))
        self.cb_tray.toggled.connect(self.save_settings)
        tray_layout.addWidget(self.cb_tray)
        tray_group.setLayout(tray_layout)
        layout.addWidget(tray_group)

        # 2. Telegram
        tg_group = QGroupBox("Telegram Bot")
        tg_layout = QFormLayout()
        self.cb_tg = QCheckBox("Enable Telegram Alerts")
        self.cb_tg.setChecked(self.config.get('telegram', {}).get('enabled', False))
        self.cb_tg.toggled.connect(self.save_settings)
        
        self.txt_tg_token = QLineEdit(self.config.get('telegram', {}).get('bot_token', ''))
        self.txt_tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_tg_chat = QLineEdit(str(self.config.get('telegram', {}).get('chat_id', '')))
        
        self.btn_test_tg = QPushButton("Test Telegram")
        self.btn_test_tg.clicked.connect(self.test_telegram)
        
        tg_layout.addRow(self.cb_tg)
        tg_layout.addRow("Bot Token:", self.txt_tg_token)
        tg_layout.addRow("Chat ID:", self.txt_tg_chat)
        tg_layout.addRow("", self.btn_test_tg)
        tg_group.setLayout(tg_layout)
        layout.addWidget(tg_group)

        # 3. Email
        email_group = QGroupBox("Email (SMTP)")
        email_layout = QFormLayout()
        self.cb_email = QCheckBox("Enable Email Alerts")
        self.cb_email.setChecked(self.config.get('email', {}).get('enabled', False))
        self.cb_email.toggled.connect(self.save_settings)
        
        self.txt_email_sender = QLineEdit(self.config.get('email', {}).get('sender', ''))
        self.txt_email_pass = QLineEdit(self.config.get('email', {}).get('password', ''))
        self.txt_email_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_email_to = QLineEdit(",".join(self.config.get('email', {}).get('recipients', [])))
        
        self.btn_test_email = QPushButton("Test Email")
        self.btn_test_email.clicked.connect(self.test_email)
        
        email_layout.addRow(self.cb_email)
        email_layout.addRow("Sender Email:", self.txt_email_sender)
        email_layout.addRow("App Password:", self.txt_email_pass)
        email_layout.addRow("Send To:", self.txt_email_to)
        email_layout.addRow("", self.btn_test_email)
        email_group.setLayout(email_layout)
        layout.addWidget(email_group)
        
        # Save Button
        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        
        # Set container to scroll area
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def save_settings(self):
        """Save settings back to config.yaml and update running instance."""
        
        # Update config dictionary
        if 'tray' not in self.config: self.config['tray'] = {}
        self.config['tray']['enabled'] = self.cb_tray.isChecked()
        
        if 'telegram' not in self.config: self.config['telegram'] = {}
        self.config['telegram']['enabled'] = self.cb_tg.isChecked()
        self.config['telegram']['bot_token'] = self.txt_tg_token.text().strip()
        self.config['telegram']['chat_id'] = self.txt_tg_chat.text().strip()
        
        if 'email' not in self.config: self.config['email'] = {}
        self.config['email']['enabled'] = self.cb_email.isChecked()
        self.config['email']['sender'] = self.txt_email_sender.text().strip()
        self.config['email']['password'] = self.txt_email_pass.text().strip()
        recipients = [r.strip() for r in self.txt_email_to.text().split(",") if r.strip()]
        self.config['email']['recipients'] = recipients
        
        # Write to file
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            logger.info("Alert settings saved to config.yaml")
            
            # Apply to running instances if provided
            if self.notification_manager:
                if self.notification_manager.tray:
                    self.notification_manager.tray.enabled = self.cb_tray.isChecked()
                
                self.notification_manager.telegram.enabled = self.cb_tg.isChecked()
                self.notification_manager.telegram.token = self.txt_tg_token.text().strip()
                self.notification_manager.telegram.chat_id = self.txt_tg_chat.text().strip()
                if self.cb_tg.isChecked() and self.notification_manager.telegram.bot is None:
                    self.notification_manager.telegram._init_bot()
                    
                self.notification_manager.email.enabled = self.cb_email.isChecked()
                self.notification_manager.email.sender = self.txt_email_sender.text().strip()
                self.notification_manager.email.password = self.txt_email_pass.text().strip()
                self.notification_manager.email.recipients = recipients
                
        except Exception as e:
            logger.error(f"Failed to save alert settings: {e}")
            QMessageBox.critical(self, "Error", f"Could not save config: {e}")
            
    def test_telegram(self):
        self.save_settings()
        if self.notification_manager and self.notification_manager.telegram:
            success = self.notification_manager.telegram.test_connection()
            if success:
                QMessageBox.information(self, "Success", "Telegram test message sent successfully!")
            else:
                QMessageBox.warning(self, "Failed", "Telegram test failed. Check token/chat ID and logs.")
                
    def test_email(self):
        self.save_settings()
        if self.notification_manager and self.notification_manager.email:
            success = self.notification_manager.email.test_connection()
            if success:
                QMessageBox.information(self, "Success", "Email test sent successfully!")
            else:
                QMessageBox.warning(self, "Failed", "Email test failed. Check credentials and logs.")
