# ⚡ Blinkit Stock Tracker Pro

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI](https://img.shields.io/badge/GUI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Automation](https://img.shields.io/badge/Automation-Selenium-green.svg)](https://www.selenium.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A desktop Windows application to track out-of-stock items on **Blinkit** in the background and receive instant **Telegram notifications** and **PC audio alarms** the second products become available.

---

## ✨ Key Features

- **🔇 Silent Background Operation (Headless Chrome)**:
  - Chrome runs 100% in the background (`--headless=new`).
  - **No open browser windows or tabs** cluttering your screen while tracking!
- **📍 Location & Persistent Login Session**:
  - One-click **"📍 Set Location / Login"** button opens a normal browser window once to log in and select your delivery address/pincode.
  - Cookies and address are saved locally in `bot_profile/` and reused silently across scans.
- **📦 Dynamic Item Management**:
  - Add, remove, or toggle tracking for individual items with custom names and Blinkit URLs.
  - Live status chips: `IN STOCK! 🎉`, `Out of Stock`, `Checking...`, `Error`, `Idle`.
  - Direct `🔗 Open` link button to jump straight to the product page when notified.
  - Automatic `https://` protocol normalization.
- **✈️ Dedicated Telegram Notification Setup & Studio**:
  - Dedicated **Telegram Setup** section in the main navigation and accessible via the top bar.
  - **🗗 Standalone Pop-out Window**: Pop out the setup guide into an independent floating window.
  - **One-Click Bot Token Verification**: Tests your token via the Telegram Bot API and detects your bot's name and `@username`.
  - **One-Click Chat ID Auto-Detection**: Reads the latest `/start` or message sent to your bot so you don't have to look up your numeric ID manually.
  - Support for personal chats, group chats, and channel notifications.
  - Live test alert dispatcher with instant error diagnostics (e.g., HTTP 400 Bad Request, 401 Unauthorized, 403 Forbidden).
- **🔔 PC Sound Alarms**:
  - Multi-beep Windows audio alarm when an item is detected in stock.
- **📜 Live Activity Logs**:
  - Color-coded activity feed with timestamps and next-scan countdown timer.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Windows 10 / 11**
- **Python 3.10 or newer** ([Download Python](https://www.python.org/downloads/))
- **Google Chrome** browser installed

### 2. Installation
1. Clone this repository or download the ZIP:
   ```bash
   git clone https://github.com/your-username/blinkit-stock-tracker.git
   cd blinkit-stock-tracker
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Launching the App
- **Option A (One-Click Launcher)**: Double-click **`Launch_Blinkit_Tracker.bat`** (launches silently with no terminal window).
- **Option B (Command Line)**:
  ```bash
  python app.py
  ```

---

## 🛠️ Initial Setup Instructions

### Step 1: Set Your Delivery Address
1. In the top header of the app, click **"📍 Set Location / Login"**.
2. A visible Chrome window will open.
3. Select your delivery address or pincode on Blinkit (and log in with OTP if desired).
4. Close the browser window when done. Your location and session are permanently saved locally.

### Step 2: Configure Your Personal Telegram Alerts
Everyone has their own Telegram account. Follow the built-in 4-step wizard in the **`✈️ Telegram Setup`** tab:
1. **Create your Bot**: Open Telegram, search for `@BotFather`, send `/newbot`, and follow prompts to obtain your **HTTP API Token**.
2. **Start Conversation**: Search for your bot's `@username` in Telegram and click **START** (or send `/start`).
3. **Get your Chat ID**: Click **"🔍 Auto-Detect Chat ID"** in the app to fetch your ID automatically, or use `@userinfobot`.
4. **Test & Save**: Click **"📩 Send Test Telegram Notification"** to verify delivery, then click **"💾 Save Telegram Settings"**.

### Step 3: Add Items & Start Tracking
1. Go to **"📦 Monitored Items"**.
2. Paste the Blinkit product URL and give it a name, then click **"➕ Add Item"**.
3. Click the green **"▶ Start Tracking"** button. The app will now silently monitor your items in the background!

---

## 📁 Project Structure

```
Blinkit/
├── app.py                      # Main desktop application (CustomTkinter GUI)
├── tracker_engine.py           # Background monitoring engine (Headless Selenium)
├── config_manager.py           # Thread-safe atomic JSON configuration manager
├── config.example.json         # Configuration template (safe for version control)
├── requirements.txt            # Python dependencies
├── Launch_Blinkit_Tracker.bat  # Silent double-click Windows launcher
├── Launch_Debug_Console.bat    # Debug launcher with live console window
├── blinkitbot.py               # Standalone CLI alternative script
├── .gitignore                  # Git ignore rules (protects credentials & cache)
├── LICENSE                     # MIT Open Source License
└── README.md                   # Project documentation
```

---

## 🔒 Security & Privacy

- **Your credentials are kept local**: Your Telegram Bot Token, Chat ID, and delivery address are stored strictly in your local `config.json` and `bot_profile/` directory.
- **Git Protection**: `.gitignore` is pre-configured to exclude `config.json` and `bot_profile/` so personal credentials, session tokens, and cookies are **never** accidentally pushed to GitHub.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
