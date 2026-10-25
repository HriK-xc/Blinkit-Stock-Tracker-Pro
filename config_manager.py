import json
import os
import uuid
import copy
import threading

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "check_interval": 60,
    "headless": True,
    "enable_telegram": True,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "enable_sound": True,
    "sound_beeps": 5,
    "stop_item_when_found": True,
    "items": []
}

class ConfigManager:
    def __init__(self, filepath=CONFIG_FILE):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.config = self.load()

    def load(self):
        with self.lock:
            if not os.path.exists(self.filepath):
                self._save_unlocked(DEFAULT_CONFIG)
                return copy.deepcopy(DEFAULT_CONFIG)
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge with default keys if missing
                    merged = copy.deepcopy(DEFAULT_CONFIG)
                    merged.update(data)
                    return merged
            except Exception:
                return copy.deepcopy(DEFAULT_CONFIG)

    def save(self):
        with self.lock:
            self._save_unlocked(self.config)

    def _save_unlocked(self, data):
        try:
            temp_filepath = self.filepath + ".tmp"
            with open(temp_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Atomic replace to prevent corrupted config files on power loss / crash
            if os.path.exists(temp_filepath):
                if os.path.exists(self.filepath):
                    os.replace(temp_filepath, self.filepath)
                else:
                    os.rename(temp_filepath, self.filepath)
        except Exception as e:
            # Fallback direct write
            try:
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as err:
                print(f"Error saving config: {err}")

    def get(self, key, default=None):
        with self.lock:
            val = self.config.get(key, default)
            return copy.deepcopy(val) if isinstance(val, (list, dict)) else val

    def set(self, key, value):
        with self.lock:
            self.config[key] = value
            self._save_unlocked(self.config)

    def get_items(self):
        with self.lock:
            return copy.deepcopy(self.config.get("items", []))

    def add_item(self, name, url):
        with self.lock:
            new_item = {
                "id": str(uuid.uuid4())[:8],
                "name": name.strip(),
                "url": url.strip(),
                "enabled": True,
                "last_status": "Idle",
                "last_checked": ""
            }
            self.config.setdefault("items", []).append(new_item)
            self._save_unlocked(self.config)
            return copy.deepcopy(new_item)

    def update_item_status(self, item_id, status, last_checked):
        with self.lock:
            for it in self.config.get("items", []):
                if it.get("id") == item_id or it.get("name") == item_id:
                    it["last_status"] = status
                    it["last_checked"] = last_checked
                    break
            self._save_unlocked(self.config)

    def delete_item(self, item_id):
        with self.lock:
            self.config["items"] = [it for it in self.config.get("items", []) if it.get("id") != item_id]
            self._save_unlocked(self.config)

    def toggle_item(self, item_id, enabled):
        with self.lock:
            for it in self.config.get("items", []):
                if it.get("id") == item_id:
                    it["enabled"] = enabled
                    break
            self._save_unlocked(self.config)
