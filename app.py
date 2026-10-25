import os
import sys
import time
import queue
import webbrowser
import threading
import requests
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from config_manager import ConfigManager
from tracker_engine import TrackerEngine

# Configure default customtkinter appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class BlinkitApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Blinkit Stock Tracker Pro")
        self.geometry("1080x760")
        self.minsize(940, 640)

        # Initialize Config & Engine
        self.config_mgr = ConfigManager()
        self.ui_queue = queue.Queue()
        
        self.engine = TrackerEngine(
            config_manager=self.config_mgr,
            on_log=self._queue_log,
            on_status_update=self._queue_status_update,
            on_cycle_tick=self._queue_tick,
            on_state_change=self._queue_state_change
        )

        # UI State variables
        self.item_cards = {}
        self.next_tick_seconds = 0
        self.is_monitoring = False

        # Telegram state variables
        self.var_tg_enabled = tk.BooleanVar(value=bool(self.config_mgr.get("enable_telegram", True)))
        self.var_tg_token = tk.StringVar(value=str(self.config_mgr.get("telegram_bot_token", "")).strip())
        self.var_tg_chat_id = tk.StringVar(value=str(self.config_mgr.get("telegram_chat_id", "")).strip())
        self.var_tg = self.var_tg_enabled  # Alias for backward compatibility
        self.discovered_bot_username = ""
        self.discovered_bot_name = ""
        self._tg_toplevel = None
        self._tg_status_badges = []
        self._tg_verify_labels = []
        self._tg_detect_labels = []
        self._tg_test_labels = []

        # Auto-update status badges whenever credentials change
        self.var_tg_enabled.trace_add("write", lambda *args: self._update_all_tg_status_badges())
        self.var_tg_token.trace_add("write", lambda *args: self._update_all_tg_status_badges())
        self.var_tg_chat_id.trace_add("write", lambda *args: self._update_all_tg_status_badges())

        # Build UI
        self._build_header()
        self._build_main_layout()

        # Update initial Telegram badges
        self._update_all_tg_status_badges()

        # Start periodic queue processor on main GUI thread
        self.after(100, self._process_ui_queue)

        # Graceful close handling
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Pre-verify bot in background if token exists
        if self.var_tg_token.get().strip():
            threading.Thread(target=self._initial_bot_lookup, daemon=True).start()

    # =========================================================================
    #                               SAFE HELPERS
    # =========================================================================

    def _safe_configure(self, widget, **kwargs):
        """Safely configure a widget without crashing if it has been destroyed."""
        try:
            if widget and widget.winfo_exists():
                widget.configure(**kwargs)
        except Exception:
            pass

    def _safe_open_url(self, url):
        """Opens URL in external browser, strictly checking for valid web schemes."""
        if not url:
            return
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
        except Exception as e:
            self._append_log_message(f"[System] Could not open browser URL: {e}", "WARNING")

    # =========================================================================
    #                                UI BUILDERS
    # =========================================================================

    def _build_header(self):
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#18181b")
        self.header_frame.pack(fill="x", padx=0, pady=0)

        # Brand / Title
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=24, pady=16)

        title_lbl = ctk.CTkLabel(
            title_box, 
            text="⚡ Blinkit Stock Tracker", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#f4f4f5"
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box, 
            text="Silent Background Stock Monitor with Telegram & Sound Alerts",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa"
        )
        subtitle_lbl.pack(anchor="w")

        # Top Control Buttons
        actions_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        actions_box.pack(side="right", padx=24, pady=16)

        # Status badge
        self.status_badge = ctk.CTkLabel(
            actions_box,
            text="● IDLE / STOPPED",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#71717a",
            fg_color="#27272a",
            corner_radius=8,
            padx=12,
            pady=6
        )
        self.status_badge.pack(side="left", padx=(0, 10))

        # Telegram Setup button in Header
        self.btn_open_telegram = ctk.CTkButton(
            actions_box,
            text="✈️ Telegram Setup",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0369a1",
            hover_color="#0284c7",
            height=38,
            command=self._show_telegram_tab
        )
        self.btn_open_telegram.pack(side="left", padx=(0, 10))

        # Setup browser button
        self.btn_setup_browser = ctk.CTkButton(
            actions_box,
            text="📍 Set Location / Login",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#3f3f46",
            hover_color="#52525b",
            height=38,
            command=self._on_setup_browser
        )
        self.btn_setup_browser.pack(side="left", padx=(0, 10))

        # Big Start / Stop Button
        self.btn_toggle_monitor = ctk.CTkButton(
            actions_box,
            text="▶ Start Tracking",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            height=38,
            width=145,
            command=self._on_toggle_monitor
        )
        self.btn_toggle_monitor.pack(side="left")

    def _build_main_layout(self):
        # Tabs container
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(12, 16))

        self.tab_items = self.tabview.add("📦 Monitored Items")
        self.tab_telegram = self.tabview.add("✈️ Telegram Setup")
        self.tab_settings = self.tabview.add("⚙️ Settings")
        self.tab_logs = self.tabview.add("📜 Live Activity Logs")

        self._build_items_tab()
        self._build_telegram_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    # --- ITEMS TAB ---
    def _build_items_tab(self):
        tab = self.tab_items

        # Top Bar: Add Item Form
        add_frame = ctk.CTkFrame(tab, fg_color="#27272a", corner_radius=10)
        add_frame.pack(fill="x", padx=10, pady=(6, 12))

        lbl_add = ctk.CTkLabel(add_frame, text="Add New Item:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_add.grid(row=0, column=0, padx=(14, 8), pady=12, sticky="w")

        self.entry_item_name = ctk.CTkEntry(add_frame, placeholder_text="Item Name (e.g. Ferrari 12Cilindri)", width=220)
        self.entry_item_name.grid(row=0, column=1, padx=6, pady=12)

        self.entry_item_url = ctk.CTkEntry(add_frame, placeholder_text="Blinkit Product URL (https://blinkit.com/prn/...)", width=430)
        self.entry_item_url.grid(row=0, column=2, padx=6, pady=12)

        btn_add = ctk.CTkButton(
            add_frame, 
            text="➕ Add Item", 
            width=110,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_add_item
        )
        btn_add.grid(row=0, column=3, padx=(8, 14), pady=12)

        # Scrollable Frame for Items
        self.items_scroll = ctk.CTkScrollableFrame(tab, label_text="Configured Items Queue", fg_color="transparent")
        self.items_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        # Refresh the items list display
        self._refresh_items_list()

    def _refresh_items_list(self):
        for widget in self.items_scroll.winfo_children():
            widget.destroy()
        self.item_cards.clear()

        items = self.config_mgr.get_items()
        if not items:
            empty_lbl = ctk.CTkLabel(
                self.items_scroll, 
                text="No items configured. Use the form above to add an item to monitor.",
                text_color="#71717a",
                font=ctk.CTkFont(size=14)
            )
            empty_lbl.pack(pady=40)
            return

        for item in items:
            self._render_item_card(item)

    def _render_item_card(self, item):
        item_id = item.get("id")
        name = item.get("name", "Unnamed")
        url = item.get("url", "")
        enabled = item.get("enabled", True)
        last_status = item.get("last_status", "Idle")
        last_checked = item.get("last_checked", "Never")

        card = ctk.CTkFrame(self.items_scroll, fg_color="#1e1e24", corner_radius=10, border_width=1, border_color="#2e2e38")
        card.pack(fill="x", padx=6, pady=6)

        # Left: Checkbox for toggle & Name
        left_box = ctk.CTkFrame(card, fg_color="transparent")
        left_box.pack(side="left", padx=14, pady=10, fill="x", expand=True)

        header_row = ctk.CTkFrame(left_box, fg_color="transparent")
        header_row.pack(anchor="w")

        toggle_var = tk.BooleanVar(value=enabled)
        chk = ctk.CTkCheckBox(
            header_row, 
            text="", 
            variable=toggle_var,
            width=20,
            command=lambda i=item_id, v=toggle_var: self._on_toggle_item(i, v)
        )
        chk.pack(side="left", padx=(0, 8))

        lbl_name = ctk.CTkLabel(
            header_row, 
            text=name, 
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#f4f4f5" if enabled else "#71717a"
        )
        lbl_name.pack(side="left")

        # URL row
        lbl_url = ctk.CTkLabel(
            left_box, 
            text=url, 
            font=ctk.CTkFont(size=11), 
            text_color="#38bdf8", 
            cursor="hand2"
        )
        lbl_url.pack(anchor="w", pady=(2, 0))
        lbl_url.bind("<Button-1>", lambda e, u=url: self._safe_open_url(u))

        # Subtext: Last checked
        lbl_checked = ctk.CTkLabel(
            left_box,
            text=f"Last Checked: {last_checked if last_checked else 'Not checked yet'}",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa"
        )
        lbl_checked.pack(anchor="w", pady=(2, 0))

        # Right: Status chip & Action buttons
        right_box = ctk.CTkFrame(card, fg_color="transparent")
        right_box.pack(side="right", padx=14, pady=10)

        # Status badge chip
        chip_fg, chip_text_color = self._get_status_colors(last_status)
        lbl_status = ctk.CTkLabel(
            right_box,
            text=last_status,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=chip_fg,
            text_color=chip_text_color,
            corner_radius=8,
            padx=12,
            pady=4
        )
        lbl_status.pack(side="left", padx=(0, 12))

        # Open in Browser button
        btn_open = ctk.CTkButton(
            right_box,
            text="🔗 Open",
            width=65,
            height=30,
            fg_color="#3f3f46",
            hover_color="#52525b",
            font=ctk.CTkFont(size=12),
            command=lambda u=url: self._safe_open_url(u)
        )
        btn_open.pack(side="left", padx=(0, 8))

        # Delete button
        btn_del = ctk.CTkButton(
            right_box,
            text="✕",
            width=32,
            height=30,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda i=item_id: self._on_delete_item(i)
        )
        btn_del.pack(side="left")

        # Store references for dynamic status updates
        self.item_cards[item_id] = {
            "card": card,
            "status_lbl": lbl_status,
            "checked_lbl": lbl_checked,
            "name_lbl": lbl_name,
            "toggle_var": toggle_var
        }

    def _get_status_colors(self, status):
        if "IN STOCK" in status.upper() or "VICTORY" in status.upper():
            return "#15803d", "#dcfce7"
        elif "CHECKING" in status.upper():
            return "#854d0e", "#fef9c3"
        elif "ERROR" in status.upper():
            return "#991b1b", "#fee2e2"
        elif "OUT OF STOCK" in status.upper():
            return "#3f3f46", "#e4e4e7"
        else:
            return "#27272a", "#a1a1aa"

    # =========================================================================
    #                      TELEGRAM SETUP TAB & WINDOW
    # =========================================================================

    def _build_telegram_tab(self):
        tab = self.tab_telegram
        self._render_telegram_setup_panel(tab, is_popup=False)

    def _render_telegram_setup_panel(self, parent_frame, is_popup=False):
        scroll = ctk.CTkScrollableFrame(parent_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=8)

        # -------------------------------------------------------------
        # TOP CARD: Header, Master Toggle, Status, and Controls
        # -------------------------------------------------------------
        top_card = ctk.CTkFrame(scroll, fg_color="#18181b", corner_radius=12, border_width=1, border_color="#27272a")
        top_card.pack(fill="x", pady=(0, 14), padx=4)

        head_row = ctk.CTkFrame(top_card, fg_color="transparent")
        head_row.pack(fill="x", padx=16, pady=(14, 8))

        title_box = ctk.CTkFrame(head_row, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)

        lbl_tg_title = ctk.CTkLabel(
            title_box,
            text="✈️ Personal Telegram Notification Setup",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#f4f4f5"
        )
        lbl_tg_title.pack(anchor="w")

        lbl_tg_sub = ctk.CTkLabel(
            title_box,
            text="Follow this simple 4-step wizard to configure your Telegram bot for instant stock notifications.",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left"
        )
        lbl_tg_sub.pack(anchor="w", pady=(2, 0))

        # Action buttons top right
        actions_top = ctk.CTkFrame(head_row, fg_color="transparent")
        actions_top.pack(side="right")

        if not is_popup:
            btn_popup = ctk.CTkButton(
                actions_top,
                text="🗗 Pop-out Window",
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#27272a",
                hover_color="#3f3f46",
                height=32,
                width=135,
                command=self._open_telegram_window
            )
            btn_popup.pack(side="left", padx=(0, 8))

        btn_tg_web = ctk.CTkButton(
            actions_top,
            text="🌐 Telegram Web",
            font=ctk.CTkFont(size=12),
            fg_color="#3f3f46",
            hover_color="#52525b",
            height=32,
            width=120,
            command=lambda: self._safe_open_url("https://web.telegram.org")
        )
        btn_tg_web.pack(side="left")

        # Master Toggle & Dynamic Status Bar
        toggle_bar = ctk.CTkFrame(top_card, fg_color="#222227", corner_radius=8)
        toggle_bar.pack(fill="x", padx=16, pady=(4, 14))

        sw_tg = ctk.CTkSwitch(
            toggle_bar,
            text="Enable Telegram Notifications",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.var_tg_enabled,
            command=self._on_tg_switch_toggled
        )
        sw_tg.pack(side="left", padx=14, pady=10)

        status_badge = ctk.CTkLabel(
            toggle_bar,
            text="● TELEGRAM: CHECKING...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#27272a",
            text_color="#a1a1aa",
            corner_radius=8,
            padx=12,
            pady=5
        )
        status_badge.pack(side="right", padx=14, pady=10)
        self._tg_status_badges.append(status_badge)

        # -------------------------------------------------------------
        # STEP 1 CARD: Create Bot with @BotFather
        # -------------------------------------------------------------
        s1_card = ctk.CTkFrame(scroll, fg_color="#1e1e24", corner_radius=10, border_width=1, border_color="#2e2e38")
        s1_card.pack(fill="x", pady=(0, 14), padx=4)

        s1_head = ctk.CTkFrame(s1_card, fg_color="transparent")
        s1_head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_s1_badge = ctk.CTkLabel(
            s1_head,
            text="STEP 1",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1d4ed8",
            text_color="#ffffff",
            corner_radius=6,
            padx=8,
            pady=3
        )
        lbl_s1_badge.pack(side="left", padx=(0, 10))

        lbl_s1_title = ctk.CTkLabel(
            s1_head,
            text="Create your Telegram Bot via @BotFather",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_s1_title.pack(side="left")

        btn_open_botfather = ctk.CTkButton(
            s1_head,
            text="🤖 Open @BotFather in Telegram",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=30,
            command=lambda: self._safe_open_url("https://t.me/BotFather")
        )
        btn_open_botfather.pack(side="right")

        s1_steps_txt = (
            "1. Open Telegram on your phone or PC and search for @BotFather (or click the blue button above).\n"
            "2. Send the message:  /newbot\n"
            "3. Choose a friendly display name (e.g. My Blinkit Alerts).\n"
            "4. Choose a unique username ending in 'bot' (e.g. john_blinkit_tracker_bot).\n"
            "5. @BotFather will reply with your HTTP API Token (formatted like: 1234567890:AAH_XYZ...).\n"
            "6. Copy that token and paste it into the field below, then click 'Verify Token':"
        )
        lbl_s1_steps = ctk.CTkLabel(
            s1_card,
            text=s1_steps_txt,
            font=ctk.CTkFont(size=12),
            text_color="#d4d4d8",
            justify="left",
            anchor="w"
        )
        lbl_s1_steps.pack(fill="x", padx=16, pady=(0, 10))

        token_row = ctk.CTkFrame(s1_card, fg_color="transparent")
        token_row.pack(fill="x", padx=16, pady=(0, 6))

        lbl_token = ctk.CTkLabel(token_row, text="Bot Token:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_token.pack(side="left", padx=(0, 10))

        entry_token = ctk.CTkEntry(
            token_row,
            textvariable=self.var_tg_token,
            placeholder_text="Paste your Telegram bot token here (e.g. 1234567890:AAH_XYZ...)",
            width=500
        )
        entry_token.pack(side="left", fill="x", expand=True, padx=(0, 10))

        lbl_verify_status = ctk.CTkLabel(
            s1_card,
            text="Ready. Click 'Verify Token' to test your token.",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left",
            anchor="w"
        )

        btn_verify = ctk.CTkButton(
            token_row,
            text="🔎 Verify Token",
            width=125,
            height=32,
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._on_verify_token(lbl_verify_status)
        )
        btn_verify.pack(side="left")

        lbl_verify_status.pack(fill="x", padx=16, pady=(0, 14))
        self._tg_verify_labels.append(lbl_verify_status)

        # -------------------------------------------------------------
        # STEP 2 CARD: Start Conversation with Bot
        # -------------------------------------------------------------
        s2_card = ctk.CTkFrame(scroll, fg_color="#1e1e24", corner_radius=10, border_width=1, border_color="#2e2e38")
        s2_card.pack(fill="x", pady=(0, 14), padx=4)

        s2_head = ctk.CTkFrame(s2_card, fg_color="transparent")
        s2_head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_s2_badge = ctk.CTkLabel(
            s2_head,
            text="STEP 2",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#7c3aed",
            text_color="#ffffff",
            corner_radius=6,
            padx=8,
            pady=3
        )
        lbl_s2_badge.pack(side="left", padx=(0, 10))

        lbl_s2_title = ctk.CTkLabel(
            s2_head,
            text="Start a Conversation with your Bot (Required by Telegram)",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_s2_title.pack(side="left")

        btn_open_my_bot = ctk.CTkButton(
            s2_head,
            text="💬 Open My Bot in Telegram",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#6d28d9",
            hover_color="#5b21b6",
            height=30,
            command=self._open_my_bot
        )
        btn_open_my_bot.pack(side="right")

        s2_steps_txt = (
            "⚠️ CRITICAL TELEGRAM RULE: Bots cannot send you messages first to protect users from spam!\n"
            "If you do not click 'START' on your bot first, Telegram will block all alerts!\n\n"
            "1. Search for your bot username in Telegram (or click the purple button above).\n"
            "2. Open the chat and click 'START' at the bottom (or send: /start).\n"
            "3. Send any short message (like 'hi'). This grants the bot permission to message you."
        )
        lbl_s2_steps = ctk.CTkLabel(
            s2_card,
            text=s2_steps_txt,
            font=ctk.CTkFont(size=12),
            text_color="#d4d4d8",
            justify="left",
            anchor="w"
        )
        lbl_s2_steps.pack(fill="x", padx=16, pady=(0, 14))

        # -------------------------------------------------------------
        # STEP 3 CARD: Find & Enter your Telegram Chat ID
        # -------------------------------------------------------------
        s3_card = ctk.CTkFrame(scroll, fg_color="#1e1e24", corner_radius=10, border_width=1, border_color="#2e2e38")
        s3_card.pack(fill="x", pady=(0, 14), padx=4)

        s3_head = ctk.CTkFrame(s3_card, fg_color="transparent")
        s3_head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_s3_badge = ctk.CTkLabel(
            s3_head,
            text="STEP 3",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            text_color="#ffffff",
            corner_radius=6,
            padx=8,
            pady=3
        )
        lbl_s3_badge.pack(side="left", padx=(0, 10))

        lbl_s3_title = ctk.CTkLabel(
            s3_head,
            text="Get your Telegram Chat ID",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_s3_title.pack(side="left")

        # Two detection methods
        methods_frame = ctk.CTkFrame(s3_card, fg_color="#27272a", corner_radius=8)
        methods_frame.pack(fill="x", padx=16, pady=(4, 10))

        lbl_detect_status = ctk.CTkLabel(
            s3_card,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left",
            anchor="w"
        )

        # Method A: Auto detect
        row_m1 = ctk.CTkFrame(methods_frame, fg_color="transparent")
        row_m1.pack(fill="x", padx=12, pady=(10, 6))

        lbl_m1 = ctk.CTkLabel(
            row_m1, 
            text="Option A (Automatic - Recommended):\nAfter sending /start to your bot in Step 2, click Auto-Detect:",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w"
        )
        lbl_m1.pack(side="left", fill="x", expand=True)

        btn_auto_detect = ctk.CTkButton(
            row_m1,
            text="🔍 Auto-Detect Chat ID",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#047857",
            hover_color="#065f46",
            height=32,
            width=185,
            command=lambda: self._on_auto_detect_chat_id(lbl_detect_status)
        )
        btn_auto_detect.pack(side="right", padx=(10, 0))

        # Method B: userinfobot
        row_m2 = ctk.CTkFrame(methods_frame, fg_color="transparent")
        row_m2.pack(fill="x", padx=12, pady=(4, 10))

        lbl_m2 = ctk.CTkLabel(
            row_m2, 
            text="Option B (Manual Lookup):\nOpen @userinfobot in Telegram, click Start, and copy your numeric Id:",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w"
        )
        lbl_m2.pack(side="left", fill="x", expand=True)

        btn_open_userinfobot = ctk.CTkButton(
            row_m2,
            text="🆔 Open @userinfobot",
            font=ctk.CTkFont(size=12),
            fg_color="#3f3f46",
            hover_color="#52525b",
            height=32,
            width=185,
            command=lambda: self._safe_open_url("https://t.me/userinfobot")
        )
        btn_open_userinfobot.pack(side="right", padx=(10, 0))

        lbl_group_tip = ctk.CTkLabel(
            s3_card,
            text="💡 Group Alerts: To receive alerts in a Telegram Group, add your bot as Admin, send /start in the group, and enter the group Chat ID (starts with -100).",
            font=ctk.CTkFont(size=11),
            text_color="#a1a1aa",
            justify="left",
            anchor="w"
        )
        lbl_group_tip.pack(fill="x", padx=16, pady=(0, 8))

        # Chat ID input row
        chat_row = ctk.CTkFrame(s3_card, fg_color="transparent")
        chat_row.pack(fill="x", padx=16, pady=(0, 6))

        lbl_chat = ctk.CTkLabel(chat_row, text="Telegram Chat ID:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_chat.pack(side="left", padx=(0, 10))

        entry_chat = ctk.CTkEntry(
            chat_row,
            textvariable=self.var_tg_chat_id,
            placeholder_text="Enter or paste Chat ID here (e.g. 123456789 or -100xxxxxxxx)",
            width=280
        )
        entry_chat.pack(side="left", padx=(0, 10))

        lbl_detect_status.pack(fill="x", padx=16, pady=(0, 14))
        self._tg_detect_labels.append(lbl_detect_status)

        # -------------------------------------------------------------
        # STEP 4 CARD: Test & Save Settings
        # -------------------------------------------------------------
        s4_card = ctk.CTkFrame(scroll, fg_color="#1e1e24", corner_radius=10, border_width=1, border_color="#2e2e38")
        s4_card.pack(fill="x", pady=(0, 14), padx=4)

        s4_head = ctk.CTkFrame(s4_card, fg_color="transparent")
        s4_head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_s4_badge = ctk.CTkLabel(
            s4_head,
            text="STEP 4",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#d97706",
            text_color="#ffffff",
            corner_radius=6,
            padx=8,
            pady=3
        )
        lbl_s4_badge.pack(side="left", padx=(0, 10))

        lbl_s4_title = ctk.CTkLabel(
            s4_head,
            text="Test Alert & Save Settings",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_s4_title.pack(side="left")

        lbl_test_status = ctk.CTkLabel(
            s4_card,
            text="Click 'Send Test Telegram Notification' to verify delivery to your phone/PC.",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left",
            anchor="w"
        )

        btn_action_row = ctk.CTkFrame(s4_card, fg_color="transparent")
        btn_action_row.pack(fill="x", padx=16, pady=(4, 10))

        btn_test = ctk.CTkButton(
            btn_action_row,
            text="📩 Send Test Telegram Notification",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=38,
            width=265,
            command=lambda: self._on_send_test_telegram(lbl_test_status)
        )
        btn_test.pack(side="left", padx=(0, 12))

        btn_save_tg = ctk.CTkButton(
            btn_action_row,
            text="💾 Save Telegram Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            height=38,
            width=220,
            command=self._on_save_telegram_setup
        )
        btn_save_tg.pack(side="left")

        lbl_test_status.pack(fill="x", padx=16, pady=(0, 14))
        self._tg_test_labels.append(lbl_test_status)

        # -------------------------------------------------------------
        # FAQ & TROUBLESHOOTING CARD
        # -------------------------------------------------------------
        faq_card = ctk.CTkFrame(scroll, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#2e2e38")
        faq_card.pack(fill="x", pady=(0, 20), padx=4)

        lbl_faq_title = ctk.CTkLabel(
            faq_card, 
            text="❓ Frequently Asked Questions & Troubleshooting", 
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e4e4e7"
        )
        lbl_faq_title.pack(anchor="w", padx=16, pady=(12, 6))

        faq_text = (
            "• Why does the test fail with 'Chat not found' (Error 400)?\n"
            "  -> Telegram strictly requires you to click START on your bot before it can message you. Complete Step 2!\n\n"
            "• Can I receive alerts on my phone and PC at the same time?\n"
            "  -> Yes! Telegram syncs across all your devices instantly. Alerts will pop up everywhere.\n\n"
            "• How do I send alerts to multiple family members or friends?\n"
            "  -> Create a Telegram group, add your bot as Admin, send a message in the group, and enter the group Chat ID (starts with -100).\n\n"
            "• Is there any cost or limit for Telegram alerts?\n"
            "  -> No. Telegram Bot API is 100% free and unlimited for personal notification use."
        )
        lbl_faq = ctk.CTkLabel(
            faq_card,
            text=faq_text,
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left",
            anchor="w"
        )
        lbl_faq.pack(fill="x", padx=16, pady=(0, 14))

    # --- SETTINGS TAB ---
    def _build_settings_tab(self):
        tab = self.tab_settings

        scroll_settings = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll_settings.pack(fill="both", expand=True, padx=16, pady=10)

        # 1. Background Mode Section
        bg_card = ctk.CTkFrame(scroll_settings, fg_color="#1e1e24", corner_radius=10)
        bg_card.pack(fill="x", pady=(0, 14), padx=4)

        lbl_bg_title = ctk.CTkLabel(bg_card, text="🌐 Browser Background Operation", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_bg_title.pack(anchor="w", padx=16, pady=(14, 4))

        self.var_headless = tk.BooleanVar(value=self.config_mgr.get("headless", True))
        chk_headless = ctk.CTkSwitch(
            bg_card,
            text="Run Chrome Silently in Background (Headless Mode)",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.var_headless,
            onvalue=True,
            offvalue=False
        )
        chk_headless.pack(anchor="w", padx=16, pady=6)

        desc_headless = ctk.CTkLabel(
            bg_card,
            text="When enabled, no browser windows or tabs will pop up or clutter your screen.\nYour delivery address & cookies from 'Set Location / Login' are loaded automatically.",
            font=ctk.CTkFont(size=12),
            text_color="#a1a1aa",
            justify="left"
        )
        desc_headless.pack(anchor="w", padx=16, pady=(0, 14))

        # 2. Timing Section
        time_card = ctk.CTkFrame(scroll_settings, fg_color="#1e1e24", corner_radius=10)
        time_card.pack(fill="x", pady=(0, 14), padx=4)

        lbl_time_title = ctk.CTkLabel(time_card, text="⏱️ Scan Frequency & Automation", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_time_title.pack(anchor="w", padx=16, pady=(14, 8))

        row_interval = ctk.CTkFrame(time_card, fg_color="transparent")
        row_interval.pack(anchor="w", padx=16, pady=4)

        lbl_interval = ctk.CTkLabel(row_interval, text="Check Interval (seconds):", font=ctk.CTkFont(size=13))
        lbl_interval.pack(side="left", padx=(0, 10))

        self.entry_interval = ctk.CTkEntry(row_interval, width=80)
        self.entry_interval.insert(0, str(self.config_mgr.get("check_interval", 60)))
        self.entry_interval.pack(side="left", padx=(0, 14))

        # Quick preset buttons
        for sec in [30, 60, 120, 300]:
            btn_pre = ctk.CTkButton(
                row_interval,
                text=f"{sec}s",
                width=45,
                height=28,
                fg_color="#27272a",
                hover_color="#3f3f46",
                command=lambda s=sec: self._set_interval_preset(s)
            )
            btn_pre.pack(side="left", padx=2)

        self.var_stop_found = tk.BooleanVar(value=self.config_mgr.get("stop_item_when_found", True))
        chk_stop_found = ctk.CTkSwitch(
            time_card,
            text="Automatically pause an item once it is found in stock (prevents repeated alerts)",
            font=ctk.CTkFont(size=13),
            variable=self.var_stop_found
        )
        chk_stop_found.pack(anchor="w", padx=16, pady=(10, 14))

        # 3. Telegram Alerts Section (Synchronized with Telegram Setup Tab)
        tg_card = ctk.CTkFrame(scroll_settings, fg_color="#1e1e24", corner_radius=10)
        tg_card.pack(fill="x", pady=(0, 14), padx=4)

        tg_head_row = ctk.CTkFrame(tg_card, fg_color="transparent")
        tg_head_row.pack(fill="x", padx=16, pady=(14, 6))

        lbl_tg_title = ctk.CTkLabel(tg_head_row, text="✈️ Telegram Instant Stock Alerts", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_tg_title.pack(side="left")

        settings_tg_badge = ctk.CTkLabel(
            tg_head_row,
            text="● TELEGRAM: CHECKING...",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#27272a",
            text_color="#a1a1aa",
            corner_radius=6,
            padx=10,
            pady=4
        )
        settings_tg_badge.pack(side="right")
        self._tg_status_badges.append(settings_tg_badge)

        chk_tg = ctk.CTkSwitch(
            tg_card,
            text="Enable Telegram Notifications",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.var_tg_enabled,
            command=self._on_tg_switch_toggled
        )
        chk_tg.pack(anchor="w", padx=16, pady=6)

        # Quick Setup Wizard Callout Buttons
        callout_box = ctk.CTkFrame(tg_card, fg_color="#27272a", corner_radius=8)
        callout_box.pack(fill="x", padx=16, pady=(6, 12))

        lbl_callout = ctk.CTkLabel(
            callout_box,
            text="Need instructions to create your personal Telegram bot or find your Chat ID?",
            font=ctk.CTkFont(size=12),
            text_color="#d4d4d8"
        )
        lbl_callout.pack(side="left", padx=14, pady=10)

        btn_go_setup = ctk.CTkButton(
            callout_box,
            text="👉 Open Telegram Setup Guide",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=32,
            command=self._show_telegram_tab
        )
        btn_go_setup.pack(side="right", padx=(0, 10), pady=10)

        btn_popup_guide = ctk.CTkButton(
            callout_box,
            text="🗗 Pop-out Window",
            font=ctk.CTkFont(size=12),
            fg_color="#3f3f46",
            hover_color="#52525b",
            height=32,
            command=self._open_telegram_window
        )
        btn_popup_guide.pack(side="right", padx=(0, 8), pady=10)

        # Bot Token
        lbl_tok = ctk.CTkLabel(tg_card, text="Telegram Bot Token:", font=ctk.CTkFont(size=12))
        lbl_tok.pack(anchor="w", padx=16, pady=(4, 0))
        self.entry_tg_token = ctk.CTkEntry(tg_card, textvariable=self.var_tg_token, width=540)
        self.entry_tg_token.pack(anchor="w", padx=16, pady=(2, 6))

        # Chat ID
        lbl_cid = ctk.CTkLabel(tg_card, text="Telegram Chat ID:", font=ctk.CTkFont(size=12))
        lbl_cid.pack(anchor="w", padx=16, pady=(4, 0))
        self.entry_tg_chat_id = ctk.CTkEntry(tg_card, textvariable=self.var_tg_chat_id, width=280)
        self.entry_tg_chat_id.pack(anchor="w", padx=16, pady=(2, 10))

        # Test Telegram Button in Settings
        btn_test_tg = ctk.CTkButton(
            tg_card,
            text="📩 Send Test Telegram Notification",
            width=250,
            fg_color="#0284c7",
            hover_color="#0369a1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_test_telegram
        )
        btn_test_tg.pack(anchor="w", padx=16, pady=(2, 14))

        # 4. Audio Sound Alert Section
        snd_card = ctk.CTkFrame(scroll_settings, fg_color="#1e1e24", corner_radius=10)
        snd_card.pack(fill="x", pady=(0, 14), padx=4)

        lbl_snd_title = ctk.CTkLabel(snd_card, text="🔔 PC Sound Alarm", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_snd_title.pack(anchor="w", padx=16, pady=(14, 6))

        self.var_sound = tk.BooleanVar(value=self.config_mgr.get("enable_sound", True))
        chk_sound = ctk.CTkSwitch(
            snd_card,
            text="Play audible beep alarm when an item is in stock",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.var_sound
        )
        chk_sound.pack(anchor="w", padx=16, pady=6)

        btn_test_snd = ctk.CTkButton(
            snd_card,
            text="🔊 Test Sound Alarm",
            width=180,
            fg_color="#4f46e5",
            hover_color="#4338ca",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_test_sound
        )
        btn_test_snd.pack(anchor="w", padx=16, pady=(4, 14))

        # Save Button bottom
        btn_save = ctk.CTkButton(
            scroll_settings,
            text="💾 Save Configuration",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            height=40,
            command=self._on_save_settings
        )
        btn_save.pack(fill="x", padx=4, pady=(6, 20))

    # --- LOGS TAB ---
    def _build_logs_tab(self):
        tab = self.tab_logs

        # Log toolbar
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(4, 8))

        self.lbl_countdown = ctk.CTkLabel(
            bar, 
            text="Status: Idle", 
            font=ctk.CTkFont(size=13, weight="bold"), 
            text_color="#a1a1aa"
        )
        self.lbl_countdown.pack(side="left")

        btn_clear_logs = ctk.CTkButton(
            bar,
            text="Clear Logs",
            width=90,
            height=30,
            fg_color="#3f3f46",
            hover_color="#52525b",
            font=ctk.CTkFont(size=12),
            command=self._on_clear_logs
        )
        btn_clear_logs.pack(side="right")

        # Scrollable log text box
        self.log_textbox = ctk.CTkTextbox(
            tab, 
            fg_color="#18181b", 
            text_color="#f4f4f5", 
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Pre-populate startup message
        self._append_log_message("[System] Blinkit Stock Tracker Pro ready. Click 'Start Tracking' to begin.", "INFO")

    # =========================================================================
    #                            ACTIONS & HANDLERS
    # =========================================================================

    def _show_telegram_tab(self):
        self.tabview.set("✈️ Telegram Setup")

    def _open_telegram_window(self):
        if self._tg_toplevel is not None and self._tg_toplevel.winfo_exists():
            self._tg_toplevel.lift()
            self._tg_toplevel.focus_force()
            return

        top = ctk.CTkToplevel(self)
        self._tg_toplevel = top
        top.title("✈️ Telegram Notification Setup Guide - Blinkit Stock Tracker")
        top.geometry("920x740")
        top.minsize(800, 600)

        # Center relative to parent window
        try:
            self.update_idletasks()
            px = self.winfo_x()
            py = self.winfo_y()
            pw = self.winfo_width()
            ph = self.winfo_height()
            x = max(0, px + (pw - 920) // 2)
            y = max(0, py + (ph - 740) // 2)
            top.geometry(f"920x740+{x}+{y}")
        except Exception:
            pass

        def _on_popup_close():
            self._tg_toplevel = None
            try:
                top.destroy()
            except Exception:
                pass

        top.protocol("WM_DELETE_WINDOW", _on_popup_close)

        self._render_telegram_setup_panel(top, is_popup=True)

    def _update_all_tg_status_badges(self):
        enabled = self.var_tg_enabled.get()
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat_id.get().strip()

        if not enabled:
            text = "● TELEGRAM ALERTS: DISABLED"
            fg_color = "#27272a"
            text_color = "#a1a1aa"
        elif token and chat_id:
            bot_info = f" (@{self.discovered_bot_username})" if self.discovered_bot_username else ""
            text = f"● TELEGRAM: CONFIGURED & READY{bot_info}"
            fg_color = "#14532d"
            text_color = "#4ade80"
        elif token and not chat_id:
            text = "● TELEGRAM: TOKEN SET, MISSING CHAT ID"
            fg_color = "#713f12"
            text_color = "#fde047"
        else:
            text = "● TELEGRAM: SETUP INCOMPLETE"
            fg_color = "#7f1d1d"
            text_color = "#fca5a5"

        active_badges = []
        for badge in self._tg_status_badges:
            try:
                if badge and badge.winfo_exists():
                    badge.configure(text=text, fg_color=fg_color, text_color=text_color)
                    active_badges.append(badge)
            except Exception:
                pass
        self._tg_status_badges = active_badges

    def _initial_bot_lookup(self):
        token = self.var_tg_token.get().strip()
        if not token:
            return
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if r.status_code == 200 and r.json().get("ok"):
                res = r.json().get("result", {})
                self.discovered_bot_username = res.get("username", "")
                self.discovered_bot_name = res.get("first_name", "")
                self.after(0, self._update_all_tg_status_badges)
                
                info_msg = f"🟢 Connected Bot: @{self.discovered_bot_username} ({self.discovered_bot_name})"
                active_labels = []
                for lbl in self._tg_verify_labels:
                    try:
                        if lbl and lbl.winfo_exists():
                            lbl.configure(text=info_msg, text_color="#4ade80")
                            active_labels.append(lbl)
                    except Exception:
                        pass
                self._tg_verify_labels = active_labels
        except Exception:
            pass

    def _on_tg_switch_toggled(self):
        enabled = self.var_tg_enabled.get()
        self.config_mgr.set("enable_telegram", enabled)
        self._update_all_tg_status_badges()
        status = "enabled" if enabled else "disabled"
        self._append_log_message(f"[Telegram] Telegram notifications {status}.", "INFO")

    def _on_verify_token(self, feedback_lbl):
        token = self.var_tg_token.get().strip()
        if not token:
            self._safe_configure(
                feedback_lbl,
                text="⚠️ Please enter a Bot Token from @BotFather first.",
                text_color="#fde047"
            )
            return

        self._safe_configure(feedback_lbl, text="⏳ Verifying token with Telegram API...", text_color="#38bdf8")

        def _verify():
            try:
                r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
                if r.status_code == 200 and r.json().get("ok"):
                    res = r.json().get("result", {})
                    username = res.get("username", "")
                    first_name = res.get("first_name", "")
                    self.discovered_bot_username = username
                    self.discovered_bot_name = first_name
                    msg = f"🟢 Token Verified! Bot: @{username} (Display Name: \"{first_name}\")"
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=msg, text_color="#4ade80"))
                    self.after(0, self._update_all_tg_status_badges)
                    self._queue_log(f"Verified Telegram bot: @{username}", "SUCCESS")
                elif r.status_code == 401:
                    err = "❌ Token Invalid (401 Unauthorized). Make sure you copied the full token from @BotFather."
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                else:
                    err = f"❌ Verification failed (HTTP {r.status_code}): {r.text}"
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
            except Exception as e:
                self.after(0, lambda: self._safe_configure(feedback_lbl, text=f"❌ Connection error: {e}", text_color="#f87171"))

        threading.Thread(target=_verify, daemon=True).start()

    def _open_my_bot(self):
        if self.discovered_bot_username:
            self._safe_open_url(f"https://t.me/{self.discovered_bot_username}")
            return

        token = self.var_tg_token.get().strip()
        if not token:
            messagebox.showinfo(
                "Bot Token Needed", 
                "Please paste your Bot Token from @BotFather in Step 1 first so we know your bot's username."
            )
            return

        def _lookup_and_open():
            try:
                r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
                if r.status_code == 200 and r.json().get("ok"):
                    username = r.json().get("result", {}).get("username", "")
                    if username:
                        self.discovered_bot_username = username
                        self._safe_open_url(f"https://t.me/{username}")
                        return
            except Exception:
                pass
            self._safe_open_url("https://web.telegram.org")

        threading.Thread(target=_lookup_and_open, daemon=True).start()

    def _on_auto_detect_chat_id(self, feedback_lbl):
        token = self.var_tg_token.get().strip()
        if not token:
            self._safe_configure(
                feedback_lbl,
                text="⚠️ Please enter your Bot Token in Step 1 before auto-detecting Chat ID.",
                text_color="#fde047"
            )
            return

        self._safe_configure(feedback_lbl, text="🔍 Scanning recent messages sent to your bot...", text_color="#38bdf8")

        def _detect():
            try:
                r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates?offset=-10", timeout=10)
                if r.status_code == 200:
                    updates = r.json()
                    chat_id = None
                    sender_name = "User"
                    for u in reversed(updates.get("result", [])):
                        for key in ["message", "edited_message", "channel_post", "my_chat_member", "callback_query"]:
                            obj = u.get(key)
                            if obj:
                                if key == "callback_query" and "message" in obj:
                                    obj = obj["message"]
                                chat = obj.get("chat")
                                if chat and "id" in chat:
                                    chat_id = chat["id"]
                                    sender_name = chat.get("first_name") or chat.get("title") or chat.get("username") or "User"
                                    break
                        if chat_id is not None:
                            break

                    if chat_id is not None:
                        self.after(0, lambda: self.var_tg_chat_id.set(str(chat_id)))
                        succ_msg = f"🟢 Success! Detected Chat ID: {chat_id} (User: {sender_name})"
                        self.after(0, lambda: self._safe_configure(feedback_lbl, text=succ_msg, text_color="#4ade80"))
                        self.after(0, self._update_all_tg_status_badges)
                        self._queue_log(f"Auto-detected Telegram Chat ID: {chat_id} ({sender_name})", "SUCCESS")
                    else:
                        warn = (
                            "⚠️ No messages found! Please open your bot in Telegram, click START "
                            "or send 'hello', then click Auto-Detect again."
                        )
                        self.after(0, lambda: self._safe_configure(feedback_lbl, text=warn, text_color="#fde047"))
                elif r.status_code == 401:
                    err = "❌ Invalid Bot Token (401 Unauthorized). Please check token in Step 1."
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                else:
                    err = f"❌ Telegram API returned status {r.status_code}: {r.text}"
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
            except Exception as e:
                self.after(0, lambda: self._safe_configure(feedback_lbl, text=f"❌ Network error: {e}", text_color="#f87171"))

        threading.Thread(target=_detect, daemon=True).start()

    def _on_send_test_telegram(self, feedback_lbl):
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat_id.get().strip()

        if not token or not chat_id:
            self._safe_configure(
                feedback_lbl,
                text="⚠️ Both Bot Token (Step 1) and Chat ID (Step 3) are required to send a test alert.",
                text_color="#fde047"
            )
            return

        self._safe_configure(feedback_lbl, text="⏳ Sending test notification to Telegram...", text_color="#38bdf8")

        def _send():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                text = (
                    "⚡ [Blinkit Stock Tracker Pro]\n\n"
                    "✅ SUCCESS! Telegram notifications are properly configured.\n\n"
                    "• You will receive instant alerts here the moment any monitored item comes back in stock!\n"
                    "• Alerts include item name, direct product link, and exact timestamp."
                )
                data = {"chat_id": chat_id, "text": text}
                r = requests.post(url, data=data, timeout=10)
                if r.status_code == 200:
                    succ = "🟢 SUCCESS: Test alert delivered! Check your Telegram app."
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=succ, text_color="#4ade80"))
                    self._queue_log(f"Test Telegram alert delivered to chat ID {chat_id}", "SUCCESS")
                elif r.status_code == 400:
                    err = "❌ Failed (400 Bad Request): Chat not found. Did you click START on your bot in Telegram? (Step 2)"
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                    self._queue_log(f"Test Telegram alert failed: 400 Bad Request (Chat not found)", "ERROR")
                elif r.status_code == 401:
                    err = "❌ Failed (401 Unauthorized): Invalid Bot Token."
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                    self._queue_log(f"Test Telegram alert failed: 401 Unauthorized", "ERROR")
                elif r.status_code == 403:
                    err = "❌ Failed (403 Forbidden): Bot was blocked by user or cannot initiate chat."
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                    self._queue_log(f"Test Telegram alert failed: 403 Forbidden", "ERROR")
                else:
                    err = f"❌ Telegram error ({r.status_code}): {r.text}"
                    self.after(0, lambda: self._safe_configure(feedback_lbl, text=err, text_color="#f87171"))
                    self._queue_log(f"Test Telegram alert failed ({r.status_code}): {r.text}", "ERROR")
            except Exception as e:
                self.after(0, lambda: self._safe_configure(feedback_lbl, text=f"❌ Connection error: {e}", text_color="#f87171"))
                self._queue_log(f"Test Telegram alert exception: {e}", "ERROR")

        threading.Thread(target=_send, daemon=True).start()

    def _on_save_telegram_setup(self):
        self.config_mgr.set("enable_telegram", self.var_tg_enabled.get())
        self.config_mgr.set("telegram_bot_token", self.var_tg_token.get().strip())
        self.config_mgr.set("telegram_chat_id", self.var_tg_chat_id.get().strip())
        self._update_all_tg_status_badges()
        messagebox.showinfo("Saved", "Telegram notification settings saved successfully!")
        self._append_log_message("[Config] Telegram credentials and preferences saved.", "SUCCESS")

    def _on_test_telegram(self):
        token = self.var_tg_token.get().strip()
        chat_id = self.var_tg_chat_id.get().strip()

        if not token or not chat_id:
            messagebox.showwarning("Missing Credentials", "Please enter both Bot Token and Chat ID.")
            return

        def _test():
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = {
                    "chat_id": chat_id, 
                    "text": "✅ [Blinkit Stock Tracker Pro]\n\nYour Telegram alerts are properly configured and working!"
                }
                r = requests.post(url, data=data, timeout=10)
                if r.status_code == 200:
                    self._queue_log("Telegram test message delivered successfully!", "SUCCESS")
                else:
                    self._queue_log(f"Telegram test failed (status {r.status_code}): {r.text}", "ERROR")
            except Exception as e:
                self._queue_log(f"Telegram test exception: {e}", "ERROR")

        threading.Thread(target=_test, daemon=True).start()

    def _on_toggle_monitor(self):
        if not self.is_monitoring:
            self._save_settings_silent()
            self._append_log_message("[System] Starting monitoring engine...", "INFO")
            started = self.engine.start()
            if not started:
                self._append_log_message("[System] Engine is already running or could not start.", "WARNING")
        else:
            self._append_log_message("[System] Stopping monitoring engine...", "INFO")
            self.engine.stop()

    def _on_setup_browser(self):
        if self.is_monitoring:
            messagebox.showwarning(
                "Tracker Active", 
                "Please stop active monitoring before opening the setup browser to avoid profile conflicts."
            )
            return
        
        self._append_log_message("[System] Launching visible Chrome browser for location & login setup...", "INFO")
        try:
            self.engine.open_setup_browser()
        except Exception as e:
            messagebox.showerror("Notice", str(e))

    def _on_add_item(self):
        name = self.entry_item_name.get().strip()[:100]
        url = self.entry_item_url.get().strip()

        if not name or not url:
            messagebox.showwarning("Incomplete Data", "Please enter both an Item Name and a Blinkit Product URL.")
            return

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        if "blinkit.com" not in url.lower():
            if not messagebox.askyesno("URL Warning", "The URL does not appear to be from blinkit.com. Add anyway?"):
                return

        self.config_mgr.add_item(name, url)
        self.entry_item_name.delete(0, "end")
        self.entry_item_url.delete(0, "end")
        self._refresh_items_list()
        self._append_log_message(f"[Config] Added item '{name}' for tracking.", "SUCCESS")

    def _on_delete_item(self, item_id):
        if messagebox.askyesno("Confirm Delete", "Remove this item from tracking?"):
            self.config_mgr.delete_item(item_id)
            self._refresh_items_list()
            self._append_log_message(f"[Config] Removed item id {item_id}.", "INFO")

    def _on_toggle_item(self, item_id, bool_var):
        enabled = bool_var.get()
        self.config_mgr.toggle_item(item_id, enabled)
        if item_id in self.item_cards:
            name_lbl = self.item_cards[item_id]["name_lbl"]
            name_lbl.configure(text_color="#f4f4f5" if enabled else "#71717a")
        status = "enabled" if enabled else "disabled"
        self._append_log_message(f"[Config] Item {item_id} {status}.", "INFO")

    def _set_interval_preset(self, seconds):
        self.entry_interval.delete(0, "end")
        self.entry_interval.insert(0, str(seconds))

    def _on_test_sound(self):
        self._append_log_message("Testing audio alarm...", "INFO")
        self.engine.play_sound_alert(count=3)

    def _save_settings_silent(self):
        try:
            interval = int(self.entry_interval.get().strip())
            if interval < 5:
                interval = 5
        except (ValueError, TypeError):
            interval = 60

        self.config_mgr.set("check_interval", interval)
        self.config_mgr.set("headless", self.var_headless.get())
        self.config_mgr.set("enable_telegram", self.var_tg_enabled.get())
        self.config_mgr.set("telegram_bot_token", self.var_tg_token.get().strip())
        self.config_mgr.set("telegram_chat_id", self.var_tg_chat_id.get().strip())
        self.config_mgr.set("enable_sound", self.var_sound.get())
        self.config_mgr.set("stop_item_when_found", self.var_stop_found.get())

    def _on_save_settings(self):
        self._save_settings_silent()
        messagebox.showinfo("Saved", "Settings saved successfully!")
        self._append_log_message("[Config] User configuration saved.", "SUCCESS")

    def _on_clear_logs(self):
        self.log_textbox.delete("1.0", "end")

    # =========================================================================
    #                        QUEUE & THREAD-SAFE EVENTS
    # =========================================================================

    def _queue_log(self, message, level="INFO"):
        self.ui_queue.put(("LOG", message, level))

    def _queue_status_update(self, item_id, status, time_str):
        self.ui_queue.put(("STATUS", item_id, status, time_str))

    def _queue_tick(self, remaining_sec):
        self.ui_queue.put(("TICK", remaining_sec))

    def _queue_state_change(self, is_running):
        self.ui_queue.put(("ENGINE_STATE", is_running))

    def _process_ui_queue(self):
        try:
            while True:
                event = self.ui_queue.get_nowait()
                ev_type = event[0]

                if ev_type == "LOG":
                    _, msg, level = event
                    self._append_log_message(msg, level)

                elif ev_type == "STATUS":
                    _, item_id, status, time_str = event
                    self._apply_status_update(item_id, status, time_str)

                elif ev_type == "TICK":
                    _, remaining_sec = event
                    if self.is_monitoring:
                        self.lbl_countdown.configure(
                            text=f"Status: Monitoring Active (Next scan in {remaining_sec}s)",
                            text_color="#4ade80"
                        )

                elif ev_type == "ENGINE_STATE":
                    _, is_running = event
                    self.is_monitoring = is_running
                    if is_running:
                        self.btn_toggle_monitor.configure(text="⏹ Stop Tracking", fg_color="#dc2626", hover_color="#b91c1c")
                        self.status_badge.configure(text="● RUNNING", text_color="#4ade80", fg_color="#14532d")
                        self.lbl_countdown.configure(text="Status: Monitoring Active", text_color="#4ade80")
                    else:
                        self.btn_toggle_monitor.configure(text="▶ Start Tracking", fg_color="#16a34a", hover_color="#15803d")
                        self.status_badge.configure(text="● STOPPED", text_color="#71717a", fg_color="#27272a")
                        self.lbl_countdown.configure(text="Status: Stopped", text_color="#a1a1aa")
        except queue.Empty:
            pass

        self.after(100, self._process_ui_queue)

    def _append_log_message(self, text, level="INFO"):
        prefix = ""
        if level == "SUCCESS":
            prefix = "🟢 "
        elif level == "VICTORY":
            prefix = "🎉 "
        elif level == "WARNING":
            prefix = "⚠️ "
        elif level == "ERROR":
            prefix = "❌ "
        else:
            prefix = "ℹ️ "

        formatted = f"{prefix}{text}\n"
        self.log_textbox.insert("end", formatted)
        self.log_textbox.see("end")

    def _apply_status_update(self, item_id, status, time_str):
        if item_id in self.item_cards:
            data = self.item_cards[item_id]
            chip_fg, chip_text_color = self._get_status_colors(status)
            data["status_lbl"].configure(text=status, fg_color=chip_fg, text_color=chip_text_color)
            data["checked_lbl"].configure(text=f"Last Checked: {time_str}")

            if "IN STOCK" in status and self.config_mgr.get("stop_item_when_found", True):
                data["toggle_var"].set(False)
                data["name_lbl"].configure(text_color="#71717a")

    def _on_close(self):
        if self._tg_toplevel and self._tg_toplevel.winfo_exists():
            try:
                self._tg_toplevel.destroy()
            except Exception:
                pass
            self._tg_toplevel = None

        if self.is_monitoring:
            if messagebox.askyesno("Confirm Exit", "Monitoring is actively running. Stop and exit now?"):
                self.engine.stop()
                self.destroy()
        else:
            self.destroy()


if __name__ == "__main__":
    try:
        app = BlinkitApp()
        app.mainloop()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Blinkit Stock Tracker - Error", f"A fatal error occurred:\n\n{err_msg}")
        except Exception:
            print(err_msg)
