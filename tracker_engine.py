import os
import time
import threading
import requests
from datetime import datetime

try:
    import winsound
except ImportError:
    winsound = None

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


class TrackerEngine:
    def __init__(self, config_manager, on_log=None, on_status_update=None, on_cycle_tick=None, on_state_change=None):
        self.config = config_manager
        self.on_log = on_log or (lambda msg, lvl="INFO": None)
        self.on_status_update = on_status_update or (lambda item_id, status, time_str: None)
        self.on_cycle_tick = on_cycle_tick or (lambda remaining_sec: None)
        self.on_state_change = on_state_change or (lambda is_running: None)
        
        self.bot_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_profile")
        self.driver = None
        self._thread = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._is_setup_running = False
        self._lock = threading.Lock()

    def is_running(self):
        return self._is_running

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.on_log(f"[{timestamp}] {message}", level)

    def send_telegram_alert(self, message):
        token = str(self.config.get("telegram_bot_token", "")).strip()
        chat_id = str(self.config.get("telegram_chat_id", "")).strip()
        enabled = self.config.get("enable_telegram", True)

        if not enabled or not token or not chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": message}
            resp = requests.post(url, data=data, timeout=10)
            if resp.status_code == 200:
                self.log("Telegram alert delivered successfully.", "SUCCESS")
                return True
            else:
                self.log(f"Telegram API returned code {resp.status_code}: {resp.text}", "WARNING")
                return False
        except Exception as e:
            self.log(f"Failed to send Telegram alert: {e}", "ERROR")
            return False

    def play_sound_alert(self, count=5):
        if not self.config.get("enable_sound", True):
            return

        try:
            count = int(count)
            if count <= 0:
                count = 1
        except (ValueError, TypeError):
            count = 5

        def _beep():
            if winsound:
                for _ in range(count):
                    if self._stop_event.is_set():
                        break
                    try:
                        winsound.Beep(1000, 450)
                        time.sleep(0.1)
                    except Exception:
                        break

        threading.Thread(target=_beep, daemon=True).start()

    def _create_driver(self, headless=True):
        options = Options()
        options.add_argument(f"--user-data-dir={self.bot_folder}")
        
        if headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            err_text = str(e)
            if "user data directory is already in use" in err_text:
                raise RuntimeError("Chrome profile is locked by another running Chrome process. Please close any open Chrome windows and try again.")
            raise

    def start(self):
        with self._lock:
            if self._is_running:
                return False
            self._stop_event.clear()
            self._is_running = True
            self.on_state_change(True)
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return True

    def stop(self):
        with self._lock:
            if not self._is_running:
                return
            self.log("Stopping monitoring engine...", "INFO")
            self._stop_event.set()

        # Wait for thread to finish cleanup
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=8)

        self._cleanup_driver()
        with self._lock:
            self._is_running = False
        self.on_state_change(False)
        self.log("Monitoring stopped.", "INFO")

    def _cleanup_driver(self):
        with self._lock:
            driver = self.driver
            self.driver = None
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    def _run_loop(self):
        headless = self.config.get("headless", True)
        mode_str = "Background (Headless)" if headless else "Visible Window"
        self.log(f"Initializing Chrome in {mode_str} mode...", "INFO")

        try:
            self.driver = self._create_driver(headless=headless)
            self.log("Chrome engine ready. Starting scan loop.", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to start Chrome: {e}", "ERROR")
            with self._lock:
                self._is_running = False
            self.on_state_change(False)
            return

        try:
            while not self._stop_event.is_set():
                items = [item for item in self.config.get_items() if item.get("enabled", True)]

                if not items:
                    self.log("No items enabled for tracking. Pausing for 10s...", "WARNING")
                    for _ in range(10):
                        if self._stop_event.is_set():
                            break
                        time.sleep(1)
                    continue

                for item in items:
                    if self._stop_event.is_set():
                        break

                    item_id = item.get("id")
                    item_name = item.get("name", "Unknown")
                    item_url = item.get("url", "").strip()

                    if not item_url:
                        continue

                    # Ensure valid schema
                    if not item_url.startswith("http://") and not item_url.startswith("https://"):
                        item_url = "https://" + item_url

                    self.on_status_update(item_id, "Checking...", datetime.now().strftime("%H:%M:%S"))

                    try:
                        if not self.driver:
                            break
                        self.driver.get(item_url)
                        
                        # Allow dynamic React content to render
                        for _ in range(8):
                            if self._stop_event.is_set():
                                break
                            time.sleep(0.5)

                        if self._stop_event.is_set():
                            break

                        # Detect stock using the proven Blinkit button check
                        buttons = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Add to cart') or text()='ADD']")
                        in_stock = False

                        for btn in buttons:
                            try:
                                if not btn.is_displayed():
                                    continue
                                txt = btn.text.strip().upper()
                                if not txt or (txt != "ADD" and "ADD TO CART" not in txt):
                                    continue
                                loc_y = btn.location.get('y', 9999)
                                if 50 < loc_y < 700:
                                    in_stock = True
                                    break
                            except Exception:
                                continue

                        now_str = datetime.now().strftime("%H:%M:%S")

                        if in_stock:
                            self.log(f"🎉 VICTORY! {item_name} IS IN STOCK!", "VICTORY")
                            self.on_status_update(item_id, "IN STOCK! 🎉", now_str)
                            self.config.update_item_status(item_id, "IN STOCK! 🎉", now_str)

                            # Send alerts
                            alert_msg = (
                                f"🚨 BLINKIT STOCK ALERT! 🚨\n\n"
                                f"🎉 {item_name.upper()} IS IN STOCK!\n\n"
                                f"Direct Link: {item_url}\n"
                                f"Detected at: {now_str}"
                            )
                            self.send_telegram_alert(alert_msg)
                            self.play_sound_alert(count=self.config.get("sound_beeps", 5))

                            if self.config.get("stop_item_when_found", True):
                                self.config.toggle_item(item_id, False)
                                self.log(f"Item '{item_name}' tracking paused now that it is in stock.", "INFO")
                        else:
                            self.log(f"Out of stock: {item_name}", "INFO")
                            self.on_status_update(item_id, "Out of Stock", now_str)
                            self.config.update_item_status(item_id, "Out of Stock", now_str)

                    except WebDriverException as wde:
                        now_str = datetime.now().strftime("%H:%M:%S")
                        err_msg = str(wde)
                        self.log(f"Browser error on '{item_name}': {err_msg[:120]}", "ERROR")
                        self.on_status_update(item_id, "Error", now_str)
                        self.config.update_item_status(item_id, "Error", now_str)
                        if "disconnected" in err_msg.lower() or "session deleted" in err_msg.lower():
                            self.log("Chrome driver disconnected. Stopping loop for recovery.", "ERROR")
                            break
                    except Exception as e:
                        now_str = datetime.now().strftime("%H:%M:%S")
                        self.log(f"Error checking {item_name}: {e}", "ERROR")
                        self.on_status_update(item_id, "Error", now_str)
                        self.config.update_item_status(item_id, "Error", now_str)

                    # Small delay between item checks
                    time.sleep(1.5)

                if self._stop_event.is_set():
                    break

                try:
                    interval = int(self.config.get("check_interval", 60))
                    if interval < 5:
                        interval = 5
                except (ValueError, TypeError):
                    interval = 60

                self.log(f"Cycle completed. Next scan in {interval}s...", "INFO")

                for remaining in range(interval, 0, -1):
                    if self._stop_event.is_set():
                        break
                    self.on_cycle_tick(remaining)
                    time.sleep(1)
        finally:
            self._cleanup_driver()
            with self._lock:
                self._is_running = False
            self.on_state_change(False)

    def open_setup_browser(self):
        """Opens visible Chrome so user can log in or set location interactively."""
        with self._lock:
            if self._is_running:
                raise RuntimeError("Please stop active monitoring before opening setup browser.")
            if self._is_setup_running:
                raise RuntimeError("Setup browser is already open. Please use or close the existing browser window.")
            self._is_setup_running = True

        def _launch():
            setup_driver = None
            try:
                self.log("Opening Chrome for login & location setup...", "INFO")
                options = Options()
                options.add_argument(f"--user-data-dir={self.bot_folder}")
                options.add_argument("--start-maximized")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)

                service = Service(ChromeDriverManager().install())
                setup_driver = webdriver.Chrome(service=service, options=options)
                setup_driver.get("https://blinkit.com")
                self.log("Blinkit opened. Set your delivery location or log in, then close the browser window when done.", "SUCCESS")
                
                # Keep alive until user closes the browser window
                while True:
                    try:
                        _ = setup_driver.window_handles
                        time.sleep(1)
                    except Exception:
                        break
                self.log("Setup browser closed. Profile saved.", "INFO")
            except Exception as e:
                self.log(f"Setup browser error: {e}", "ERROR")
            finally:
                if setup_driver:
                    try:
                        setup_driver.quit()
                    except Exception:
                        pass
                with self._lock:
                    self._is_setup_running = False

        t = threading.Thread(target=_launch, daemon=True)
        t.start()
        return t
