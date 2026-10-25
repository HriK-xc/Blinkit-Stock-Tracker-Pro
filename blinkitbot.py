import time
import os
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

try:
    import winsound
except ImportError:
    winsound = None

# ==========================================
#        CONFIG LOADER (FROM CONFIG.JSON)
# ==========================================

BOT_DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_profile")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

TRACKING_LIST = {}
CHECK_INTERVAL = 60
ENABLE_TELEGRAM = True
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
ENABLE_SOUND = True
SOUND_BEEPS = 5

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            CHECK_INTERVAL = int(cfg.get("check_interval", 60))
            ENABLE_TELEGRAM = bool(cfg.get("enable_telegram", True))
            TELEGRAM_BOT_TOKEN = str(cfg.get("telegram_bot_token", "")).strip()
            TELEGRAM_CHAT_ID = str(cfg.get("telegram_chat_id", "")).strip()
            ENABLE_SOUND = bool(cfg.get("enable_sound", True))
            SOUND_BEEPS = int(cfg.get("sound_beeps", 5))
            for it in cfg.get("items", []):
                if it.get("enabled", True):
                    TRACKING_LIST[it.get("name", "Item")] = it.get("url", "")
    except Exception as e:
        print(f"Notice: Could not load config.json: {e}")

# Fallback default items if none configured
if not TRACKING_LIST:
    TRACKING_LIST = {
        "Ferrari": "https://blinkit.com/prn/x/prid/746635"
    }

# ==========================================
#              MAIN SCRIPT
# ==========================================

def send_telegram_alert(message):
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data, timeout=10)
        print("-> Telegram notification sent.")
    except Exception as e:
        print(f"-> Failed to send Telegram alert: {e}")

def init_driver():
    options = Options()
    options.add_argument(f"--user-data-dir={BOT_DATA_FOLDER}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver

def check_stock(driver, name, url):
    print(f"\nChecking: {name}...")
    try:
        driver.get(url)
        time.sleep(3)

        buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'Add to cart') or text()='ADD']")
        
        is_in_stock = False
        for btn in buttons:
            try:
                if not btn.is_displayed():
                    continue
                txt = btn.text.strip().upper()
                if not txt or (txt != "ADD" and "ADD TO CART" not in txt):
                    continue
                loc_y = btn.location.get('y', 9999)
                if 50 < loc_y < 700:
                    is_in_stock = True
                    break
            except Exception:
                continue

        if is_in_stock:
            print(f"🎉 VICTORY! {name} IS IN STOCK!")
            alert_msg = f"🚨 BLINKIT STOCK ALERT! 🚨\n\n🎉 {name} IS IN STOCK!\n\nDirect Link: {url}"
            send_telegram_alert(alert_msg)
            if ENABLE_SOUND and winsound:
                for _ in range(SOUND_BEEPS):
                    winsound.Beep(1000, 450)
                    time.sleep(0.1)
            return True
        else:
            print(f"❌ Out of Stock: {name}")
            return False

    except Exception as e:
        print(f"⚠️ Error checking {name}: {e}")
        return False

def main():
    print("=" * 55)
    print("      BLINKIT STOCK TRACKER (CLI ENGINE)")
    print("=" * 55)
    
    driver = init_driver()

    try:
        while True:
            for name, url in list(TRACKING_LIST.items()):
                check_stock(driver, name, url)
                time.sleep(2)
            
            print(f"\nCycle completed. Waiting {CHECK_INTERVAL} seconds...")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopping tracker...")
    finally:
        driver.quit()
        print("Driver closed. Exiting.")

if __name__ == "__main__":
    main()
