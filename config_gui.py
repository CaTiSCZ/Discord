#config_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
#import subprocess
import threading
import asyncio
import logging
#from keyboard_listener import KeyboardListener
import main_client
from logger import Logging, CallbackHandler, setup_logger
#from web.server import start_web_server, stop_web_server


CONFIG_FILE = "config.json"

DEFAULT_WATCHER = {
    "enabled": True,
    "comment": "",
    "channel_id": "",
    "file_path": "output.txt",
    "last_id_file": "last_id.txt",
    "socket_panel": "panel-a",
    "interval": 10,
    "history_limit": 10,
    "show_author_mode": "both",
    "ignore_mode": None,
    "manual_clear": False,
    "type_output": "txt",
    "max_rows_per_column": 9,
    "max_column_width": 40,
    "header_text": "",
    "column_spacing": 2
}

def set_widget_state(widget, enable=False):
    state = 'normal' if enable else 'disabled'
    
        # rekurze pro kontejnery (Frame/LabelFrame/ttk.Frame atd.)
    children = widget.winfo_children()
    if children:
        for child in children:
            set_widget_state(child, enable=enable)
        
    try:
        # ttk widgety mají metodu state()
        if hasattr(widget, 'state') and callable(widget.state):
            if not enable:
                widget.state(['disabled'])
            else:
                widget.state(['!disabled'])
        else:
            widget.configure(state=state)
    except Exception:
        # některé widgety nemají state/configure stejným způsobem — přeskočíme je
        pass

class ConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Bot Control Panel")

        self.lockable = {}

        self.gui_size()
        

        # Inicializuj logger s GUI callbackem
        self.logging_ctx = Logging()
        self.logger = setup_logger("GUI", level=logging.DEBUG)

        # Přidej CallbackHandler pro zápis do log panelu
        self.gui_handler = CallbackHandler(sink_text=self.append_log, level=logging.DEBUG)
        self.gui_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self.gui_handler)

        self.engine = None
        self.bot_thread = None
        self.bot_running = False
        self.loop = None
        self.config = self.load_config()
        self.bot_running = False
        
        self.setup_UI()
        self.watcher_vars = [{} for _ in self.config.get("watchers", [])]
        
        
           

        # zavěsit handler pro kliknutí na křížek okna
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Přidat key bindings pro 'd' a 'q' (když je GUI aktivní okno)
        self.root.bind('<Key>', self.on_key_press)
        #self.root.bind('<q>', lambda e: self.on_key_press('q'))

        self.logger.debug("GUI initialized.")
        self.render_watchers()

    def setup_UI(self):
        # TOKEN INPUT (na jednom řádku vedle sebe)
        token_frame = tk.Frame(root)
        token_frame.pack(anchor="w", padx=10, pady=5)
        
        tk.Label(token_frame, text="Discord BOT TOKEN:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 10))
        self.token_entry = tk.Entry(token_frame, width=80)
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.token_entry.insert(0, self.config.get("TOKEN", ""))
        self.lockable["token"] = self.token_entry

        # BUTTONS (pod tokenem)
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)
        addW = tk.Button(btn_frame, text="Add Watcher", command=self.add_watcher)
        addW.pack(side="left", padx=5)
        saveBtn = tk.Button(btn_frame, text="Save Configuration", command=self.save_config)
        saveBtn.pack(side="left", padx=5)
        run = tk.Button(btn_frame, text="Run Bot", command=self.run_bot)
        run.pack(side="left", padx=5)
        tk.Button(btn_frame, text="Delete Files (d)", command=self.delete_files).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Quit Bot (q)", command=self.quit_bot).pack(side="left", padx=5)
        #tk.Button(btn_frame, text="GUI size", command=self.gui_size).pack(side="left", padx=5)
        self.lockable["ADD"] = addW
        self.lockable["SAVE"] = saveBtn
        self.lockable["RUN"] = run

        # Hlavní kontejner
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Váhy sloupců: Levý (0) se roztahuje, Pravý (1) je fixní podle obsahu
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=0)
        self.main_frame.rowconfigure(0, weight=1)

        # --- LEVÁ STRANA (LOGY) ---
        self.left_panel = ttk.LabelFrame(self.main_frame, text="System Logs", padding="5")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.left_panel.columnconfigure(0, weight=1)
        self.left_panel.rowconfigure(0, weight=1)

        self.log_text = tk.Text(self.left_panel, state='disabled', wrap='word', bg="#ffffff", fg="#000000", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        log_scroll = ttk.Scrollbar(self.left_panel, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # --- PRAVÁ STRANA (WATCHERY) ---
        self.right_panel = ttk.LabelFrame(self.main_frame, text="Watchers Configuration", padding="5")
        self.right_panel.grid(row=0, column=1, sticky="ns")

        # Seznam watcherů se scrollbarem
        self.canvas = tk.Canvas(self.right_panel, highlightthickness=0, width=700) # Pevnější šířka pro pravou stranu
        self.scrollbar = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)



    def gui_size(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = int(screen_width * 0.9)
        height = int(screen_height * 0.7)
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        
        self.root.state('zoomed')
        #self.root.geometry(f"{width}x{height}+{x}+{y}")
        #print(f"Screen size: {screen_width}x{screen_height}, GUI size: {width}x{height} at ({x},{y})")

        

    def append_log(self, text):
        # Bezpečný zápis do GUI z jakéhokoli vlákna
        self.root.after(0, self._actual_write, text)

    def _actual_write(self, text):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ----------------------------------------------------------------
    def on_key_press(self, event):
        """Handler pro stisk klávesy v GUI okně."""
        focus = self.root.focus_get()
        if not isinstance(focus, (tk.Entry, tk.Text)):
            if event.char.lower() == 'd':
                self.delete_files()
            elif event.char.lower() == 'q':
                self.quit_bot()

    # ----------------------------------------------------------------
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return {"TOKEN": "", "watchers": []}

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.logger.debug("Configuration loaded successfully.")

            # normalize watchers
            clean = []
            for w in cfg.get("watchers", []):
                new_w = DEFAULT_WATCHER.copy()
                new_w.update(w)
                clean.append(new_w)

            cfg["watchers"] = clean
            return cfg

        except json.JSONDecodeError:
            messagebox.showerror("Error", "config.json is corrupted. Creating a new one.")
            return {"TOKEN": "", "watchers": []}

    # ----------------------------------------------------------------
    def render_watchers(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.lockable = {k: v for k, v in self.lockable.items() if not k.startswith("watcher_")}
        self.watcher_vars = []
        for idx, watcher in enumerate(self.config["watchers"]):
            self.watcher_vars.append({})
            self.render_one_watcher(self.scroll_frame, idx, watcher)

    def toggle_watcher_visibility(self, var_enabled, details_frame):
            """Schová nebo zobrazí detaily watcheru."""
            if var_enabled.get():
                # Používáme pack, protože zbytek tvého GUI používá pack
                details_frame.pack(fill="x", padx=15, pady=5, after=details_frame.master.winfo_children()[0])
                # Poznámka: 'after' zajistí, že se to otevře pod hlavičkou
            else:
                details_frame.pack_forget()
    # ----------------------------------------------------------------
    def render_one_watcher(self, parent_frame, idx, watcher):
        watcher_wrapper = ttk.Frame(parent_frame)
        watcher_wrapper.pack(fill="x", padx=5, pady=5)

        self.watcher_vars[idx]["wrapper"] = watcher_wrapper

        # 2. HLAVIČKA (vždy viditelná)
        header_frame = ttk.Frame(watcher_wrapper)
        header_frame.pack(fill="x")

        enabled_var = tk.BooleanVar(value=watcher.get("enabled", True))
        self.watcher_vars[idx]["enabled"] = enabled_var

        # DETAILNÍ PANEL (Vše pod hlavičkou, co se bude schovávat)
        # Použijeme LabelFrame, aby to vypadalo jako karta
        details_frame = ttk.LabelFrame(watcher_wrapper, text=f"Nastavení sledování")

        # Checkbutton v hlavičce
        check = ttk.Checkbutton(
            header_frame, 
            text="ENABLED",
            variable=enabled_var,
            command=lambda: self.toggle_watcher_visibility(enabled_var, details_frame)
        )
        check.pack(side="left")

        # Poznámka v hlavičce (aby bylo vidět, co je to za kanál i když je sbaleno)
        ttk.Label(header_frame, text=" | Comment:").pack(side="left")
        comment_entery = tk.StringVar(value=watcher.get("comment", ""))
        self.watcher_vars[idx]["comment"] = comment_entery
        ttk.Entry(header_frame, textvariable=comment_entery, width=40).pack(side="left", padx=5)

        # Tlačítko smazat v hlavičce
        tk.Button(header_frame, text="Remove", fg="red", command=lambda: self.remove_watcher(idx)).pack(side="right")
        
        # Channel ID
        row_id = ttk.Frame(details_frame)
        row_id.pack(fill="x", padx=5, pady=2)
        ttk.Label(row_id, text="Channel ID:", width=10).pack(side="left")
        var_cid = tk.IntVar(value=watcher.get("channel_id", ""))
        self.watcher_vars[idx]["channel_id"] = var_cid
        ttk.Entry(row_id, textvariable=var_cid, width=20).pack(side="left", expand=True, padx=5)

        # File Path & Last ID File
        ttk.Label(row_id, text="Output File:", width=10).pack(side="left", padx=(10,0))
        var_path = tk.StringVar(value=watcher.get("file_path", "output.txt"))
        self.watcher_vars[idx]["file_path"] = var_path
        ttk.Entry(row_id, textvariable=var_path, width=20).pack(side="left", expand=True, padx=5)
        # Last ID File
        ttk.Label(row_id, text="Last ID File:", width=10).pack(side="left", padx=(10,0))
        var_lastid = tk.StringVar(value=watcher.get("last_id_file", "last_id.txt"))
        self.watcher_vars[idx]["last_id_file"] = var_lastid
        ttk.Entry(row_id, textvariable=var_lastid, width=20).pack(side="left", expand=True, padx=5)

        #interval, history limit, rows per column, column width
        row_limits = ttk.Frame(details_frame)
        row_limits.pack(fill="x", padx=5, pady=2)
        #interval
        ttk.Label(row_limits, text="Interval (s):").pack(side="left")
        var_interval = tk.IntVar(value=watcher.get("interval", 10))
        self.watcher_vars[idx]["interval"] = var_interval
        ttk.Entry(row_limits, textvariable=var_interval, width=5).pack(side="left", padx=5)
        # History Limit
        ttk.Label(row_limits, text="History Limit:").pack(side="left")
        var_history = tk.IntVar(value=watcher.get("history_limit", 100))
        self.watcher_vars[idx]["history_limit"] = var_history
        ttk.Entry(row_limits, textvariable=var_history, width=5).pack(side="left", padx=5)
        # Rows per Column
        ttk.Label(row_limits, text="Rows/Column:").pack(side="left", padx=(10,0))
        var_rows = tk.IntVar(value=watcher.get("max_rows_per_column", 9))
        self.watcher_vars[idx]["max_rows_per_column"] = var_rows
        ttk.Entry(row_limits, textvariable=var_rows, width=5).pack(side="left", padx=5)
        # Column Width
        ttk.Label(row_limits, text="Column Width:").pack(side="left", padx=(10,0))
        var_colwidth = tk.IntVar(value=watcher.get("max_column_width", 40))
        self.watcher_vars[idx]["max_column_width"] = var_colwidth
        ttk.Entry(row_limits, textvariable=var_colwidth, width=5).pack(side="left", padx=5)
        # Ignore Mode & Show Author
        row_modes = ttk.Frame(details_frame)

        row_modes.pack(fill="x", padx=5, pady=2)
        # Ignore Mode
        ttk.Label(row_modes, text="Ignore Mode:").pack(side="left")
        var_ignore = tk.StringVar(value=str(watcher.get("ignore_mode", "None")))
        self.watcher_vars[idx]["ignore_mode"] = var_ignore
        ignore_combo = ttk.Combobox(row_modes, textvariable=var_ignore, values=["None", "bot", "human"], width=12)
        ignore_combo.pack(side="left", padx=5)
        # Show Author
        ttk.Label(row_modes, text="Show Author:").pack(side="left", padx=(10,0))
        var_show_author = tk.StringVar(value=str(watcher.get("show_author_mode", "both")))
        self.watcher_vars[idx]["show_author"] = var_show_author
        author_combo = ttk.Combobox(row_modes, textvariable=var_show_author, values=["both", "human", "bot", "None"], width=12)
        author_combo.pack(side="left", padx=5)

        # Header Text
        row_header = ttk.Frame(details_frame)
        row_header.pack(fill="x", padx=5, pady=2)
        ttk.Label(row_header, text="Header Text:").pack(side="left")
        var_header = tk.StringVar(value=watcher.get("header_text", ""))
        self.watcher_vars[idx]["header_text"] = var_header
        ttk.Entry(row_header, textvariable=var_header, width=20).pack(side="left", padx=5)
        
        ttk.Label(row_header, text="Socket Panel:").pack(side="left", padx=(10,0))
        var_panel = tk.StringVar(value=watcher.get("socket_panel", "panel-a"))
        self.watcher_vars[idx]["socket_panel"] = var_panel
        panel_combo = ttk.Combobox(row_header, textvariable=var_panel, values=["panel-a", "panel-b"], width=10)
        panel_combo.pack(side="left", padx=5)

        ttk.Label(row_header, text="Type Output:").pack(side="left", padx=(10,0))
        var_type_output = tk.StringVar(value=watcher.get("type_output", "txt"))
        self.watcher_vars[idx]["type_output"] = var_type_output
        type_combo = ttk.Combobox(row_header, textvariable=var_type_output, values=["txt", "html", "socket"], width=10)
        type_combo.pack(side="left", padx=5)

        

        # Další nastavení (Txt Output, Manual Clear atd.)
        row_opts = ttk.Frame(details_frame)
        row_opts.pack(fill="x", padx=5, pady=2)

        var_clear = tk.BooleanVar(value=watcher.get("manual_clear", False))
        self.watcher_vars[idx]["manual_clear"] = var_clear
        ttk.Checkbutton(row_opts, text="Manual Clear", variable=var_clear).pack(side="left", padx=5)
        
        self.lockable[f"watcher_{idx}"] = watcher_wrapper
        # 3. NASTAVENÍ POČÁTEČNÍ VIDITELNOSTI
        self.toggle_watcher_visibility(enabled_var, details_frame)
        
    # ----------------------------------------------------------------
    def add_watcher(self):
        self.config["watchers"].append(DEFAULT_WATCHER.copy())
        self.render_watchers()

    # ----------------------------------------------------------------
    def remove_watcher(self, idx):
        del self.config["watchers"][idx]
        self.render_watchers()

    # ----------------------------------------------------------------
    def save_config(self):
        try:
            self.config["TOKEN"] = self.token_entry.get()
            clean_watchers = []
            #watcher by měl být třída
            for w in self.watcher_vars:
                watcher_name = w.get("comment").get() if "comment" in w else "Unknown"
                def get_int(key, default):
                    if key not in w: 
                        self.logger.warning(f" [{watcher_name}] - Key '{key}' not found; using default {default}.")
                        return default
                    try: 
                        return int(w[key].get())
                    except (ValueError, TypeError): 
                        self.logger.warning(f" [{watcher_name}] - Invalid int for key '{key}'; using default {default}.")
                        return default
                def get_str(key, default):
                    if key not in w: 
                        self.logger.warning(f" [{watcher_name}] - Key '{key}' not found; using default {default}.")
                        return default
                    return str(w[key].get())
                def get_bool(key, default):
                    if key not in w: 
                        self.logger.warning(f" [{watcher_name}] - Key '{key}' not found; using default {default}.")
                        return default
                    val = w[key].get()
                    if isinstance(val, str):
                        if val.lower() == "false": return False
                        if val.lower() == "true": return True
                    try: return bool(val)
                    except (ValueError, TypeError): 
                        self.logger.warning(f" [{watcher_name}] - Invalid bool for key '{key}'; using default {default}.")
                        return default
                def get_combo(key, default):
                    if key not in w: 
                        self.logger.warning(f" [{watcher_name}] - Key '{key}' not found; using default {default}.")
                        return default
                    val = w[key].get()
                    return None if val == "None" else str(val)
                
                clean = {
                    "enabled": get_bool("enabled", True),
                    "comment": get_str("comment", ""),
                    "channel_id": get_str("channel_id", ""),
                    "file_path": get_str("file_path", "output.txt"),
                    "last_id_file": get_str("last_id_file", "last_id.txt"),
                    "socket_panel": get_str("socket_panel", "panel-a"),
                    "interval": get_int("interval", 10),
                    "history_limit": get_int("history_limit", 10),
                    "show_author_mode": get_combo("show_author", "both"),
                    "ignore_mode": get_combo("ignore_mode", None),
                    "manual_clear": get_bool("manual_clear", False),
                    "type_output": get_combo("type_output", "txt"),
                    "header_text": get_str("header_text", ""),
                    "max_rows_per_column": get_int("max_rows_per_column", 9),
                    "max_column_width": get_int("max_column_width", 40),
                    "column_spacing": int(w.get("column_spacing", 2))
                }
                clean_watchers.append(clean)
            self.config["watchers"] = clean_watchers
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    # ----------------------------------------------------------------
    def run_bot(self):
        if self.bot_running:
            self.logger.warning("Bot already running.")
            return

        self.save_config()

        self.logger.debug("Discord bot launched. Inputs locked.")
        self.engine = main_client.DiscordEngine(self.config)
        self.loop = asyncio.new_event_loop()
        self.bot_thread = threading.Thread(
            target=self.engine.start, 
            args=(self.loop,), 
            daemon=True
        )
        self.bot_thread.start()
        self.bot_running = True
        for widget in self.lockable.values():
            set_widget_state(widget, enable=False)
        
    # ----------------------------------------------------------------
    def stop_bot(self, wait_secs: float = 1.0):
        if not self.bot_running:
            return

        self.logger.debug("Stoping bot...")
        if self.engine:
            try:
                self.engine.stop()
            except Exception as e:
                self.logger.error(f"Error while stopping engine: {e}")

        self.root.after(int(wait_secs * 1000), self._finalize_stop)

    def _finalize_stop(self):
        self.bot_running = False
        self.logger.info("Bot stopped. Inputs unlocked.")
        for widget in self.lockable.values():
            if widget: 
                set_widget_state(widget, enable=True)


    # ----------------------------------------------------------------
    def send_key_to_bot(self, key: str):
        """Emuluj stisk klávesy -> pošli do KeyboardListener (pokud běží)."""
        if not self.engine or not self.engine.kb_listener or not self.bot_running:
            self.logger.warning("Bot isn't running.")
            return
        try:
            self.engine.kb_listener.emit_key(key)
        except Exception as e:
            self.logger.error(f"Key sending failed: {e}")

    # ----------------------------------------------------------------
    def delete_files(self):
        # pokud běží bot, emuluj 'd' (watchery tak smažou svůj obsah)
        if self.bot_running:
            self.send_key_to_bot("d")
            self.logger.info("Sent key 'd' to watchers.")
            return

        # fallback: mazání souborů lokálně
        if not self.bot_running:
            self.logger.warning("Start bot for delete files.")
            return

    # ----------------------------------------------------------------
    def quit_bot(self):
        self.logger.debug("Quit bot requested.")
        # pokud běží bot a máme listener, pouze ho zastav a NEZAVÍREJ GUI
        if self.bot_running:
            self.stop_bot()
            return
        else:
            self.logger.info("Bot isn't running.")

    # ----------------------------------------------------------------
    def on_close(self):
        if self.bot_running:
            self.stop_bot()
        
        self.logging_ctx.__exit__(None, None, None) # Vypnutí loggeru
        self.root.destroy()
        sys.exit(0)

# --------------------------------------------------------------------
root = tk.Tk()
ConfigGUI(root)
root.mainloop()
