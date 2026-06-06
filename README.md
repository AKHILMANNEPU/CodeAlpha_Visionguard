# CodeAlpha_Visionguard

Visionguard is an advanced, AI-powered desktop surveillance application that provides real-time object detection, zone tracking, line-crossing detection, and intelligent alerting capabilities using YOLOv8. 

## 🚀 Features
- **Multi-Camera Support:** Connect to multiple local webcams or RTSP IP streams simultaneously.
- **Intelligent Object Detection:** Detects people, vehicles, and other objects in real-time.
- **Zone Intrusion & Line Crossing:** Draw custom polygonal zones and lines directly on the video feed.
- **Automated Alerts:** Get notified immediately when an intrusion occurs.
- **Dashboard & Analytics:** View hourly intrusion statistics, event logs, and system health in a modern PyQt6 interface.
- **Evidence Management:** Automatically saves video clips and snapshots of triggered events.

## 🎯 Outcomes
- Enhance physical security without relying on human monitoring 24/7.
- Reduce false positives by setting high-confidence AI thresholds and specific object filters.
- Maintain a structured local database of all security incidents and events.

## 🛠️ Step-by-Step Process to Use
1. **Launch the Application:** Run `VisionGuard_AI.exe` (or run `python main.py` from source).
2. **Add a Camera:** Navigate to the "Cameras" tab and click "Add Camera". Select your webcam or enter an RTSP stream URL.
3. **Set Up Rules:** Click on the "Rules" tab.
   - Use the drawing tools to sketch a "Restricted Zone" or a "Tripwire Line".
   - Select the target classes (e.g., "Person") and hit Save.
4. **Monitor the Feed:** Return to the "Live View" tab. If a person enters your drawn zone, the border will turn red, an alert will be logged, and a video clip will begin recording.
5. **View Analytics:** Check the "Dashboard" tab to see historical detection charts and recent events.

## 🔔 Setting Up Alerts

Visionguard supports both **Telegram** and **SMTP Email** alerts.

### How to Connect Telegram Bot Alerts:
1. Open the Telegram app and search for **BotFather**.
2. Send the message `/newbot` and follow the prompts to name your bot.
3. BotFather will give you a **Bot Token** (e.g., `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).
4. To get your **Chat ID**, send a message to your new bot, then visit `https://api.telegram.org/bot<YourBotToken>/getUpdates` in your browser to find your `chat.id`.
5. Open Visionguard, go to the **Settings** tab.
6. Enter your Bot Token and Chat ID under the Telegram section, and toggle "Enable Telegram Alerts".

### How to Connect SMTP Email Alerts:
1. Ensure you have a Gmail account (or other SMTP provider).
2. Go to your Google Account Settings -> Security -> 2-Step Verification.
3. Scroll down to **App Passwords** and create a new one named "Visionguard".
4. Copy the generated 16-character password.
5. Open Visionguard, go to the **Settings** tab.
6. Enter your Email Address as the Sender, your App Password, and the Recipient emails.
7. Toggle "Enable Email Alerts".

*(Note: Never commit your `config.yaml` or `.env` files with your passwords to GitHub!)*
