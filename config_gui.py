#config_gui.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser, font
import json
import os
import sys
import threading
import asyncio
import logging
from PIL import ImageGrab, Image, ImageTk
import tkinterdnd2 as tkdnd

import main_client
from logger import setup_logger, CallbackHandler, Logging
from dispatcher import dispatcher
from image_processor import upload_image, upload_image_from_pil
from web.server import sio
from gui_utils import FocusManager, WindowPositionMixIn


CONFIG_FILE = "config.json"

DEFAULT_WATCHER = {
    "enabled": True,
    "comment": "",
    "channel_id": "",
    "file_path": "temp/output",
    "socket_panel": "panel-a",
    "image_panel": "panel-o",
    "interval": 10,
    "show_author_mode": "both",
    "ignore_mode": None,
    "manual_clear": False,
    "type_output": "socket",
    "header_text": "",
    "gui_watcher": False,    
}

DEFAULT_LAYOUT = {
    "canvas": {"width": 2560, "height": 1440, "bg_preview": ""},
    "global_style": {
        "font_family": "monospace",
        "font_size": 24,
        "color": "#ffffff",
        "b_color": "#e0e0e0", # Výchozí barva pro tučné
        "b_size": "",
        "i_color": "#e0e0e0", # Výchozí barva pro kurzívu
        "i_size": "",
        "u_color": "#ffffff",
        "u_size": "",
        "s_color": "#888888",
        "s_size": ""
    },
    "panels": {
        "panel-a": {"x": 2, "y": 680, "width": 2000, "height": 350, "z_index": 5, "bold": False, "italic": False, "auto_size": True, "column_width": 650, "column_spacing": 10},
        "panel-b": {"x": 2, "y": 1020, "width": 2556, "height": 410, "z_index": 5, "bold": False, "italic": False, "auto_size": True},
        "panel-c": {"x": 1260, "y": 680, "width": 1300, "height": 350, "z_index": 5, "bold": False, "italic": False, "auto_size": True},
        "panel-d": {"x": 2, "y": 2, "width": 2556, "height": 1434, "z_index": 10,  "bold": False, "italic": False, "auto_size": True},
        "panel-e": {"x": 2, "y": 1300, "width": 2556, "height" :100,"z_index" :5,"font_size" :40, "bold" :False,"italic" :False, "auto_size" :False},
        "panel-o":{"x" :2,"y" :2,"width" :2556,"height" :1434,"z_index" :0, "img_fit": "contain", "img_opacity": 1, "is_image": True, "auto_size" :False}
    }
}
DEFAULT_TEXT_PANEL = {
    "x": 2,
    "y": 680,
    "width": 2000,
    "height": 350,
    "z_index": 5,
    "bold": False,
    "italic": False,
    "auto_size": True,
    "column_width": 650
}
DEFAULT_IMG_PANEL = {
    "x": 2,
    "y": 2,
    "width": 2556,
    "height": 1434,
    "z_index": 0,
    "img_fit": "contain",
    "img_opacity": 1,
    "is_image": True,
    "auto_size": False
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
        self.gui_handler = CallbackHandler(sink_text=self.append_log, level=logging.INFO)
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
        self.gui_texts = {}
        self.gui_watcher_frames = {}  # Mapování gui_id -> (LabelFrame, watcher_idx)

        # zavěsit handler pro kliknutí na křížek okna
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Přidat key bindings pro 'd' a 'q' (když je GUI aktivní okno)
        self.root.bind('<Key>', self.on_key_press)
        self.root.bind("<Button-1>", lambda e: self.root.focus_set() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)
        self.root.bind_class("TCombobox", "<MouseWheel>", lambda event: "break")
        self.root.bind_class("TSpinbox", "<MouseWheel>", lambda event: "break")

        self.logger.debug("GUI initialized.")
        self.render_watchers()

    def setup_UI(self):
        # TOKEN INPUT (na jednom řádku vedle sebe)
        token_frame = tk.Frame(root)
        token_frame.pack(anchor="w", padx=10, pady=5)
        
        tk.Label(token_frame, text="Discord BOT TOKEN:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 10))
        self.token_entry = tk.Entry(token_frame, width=100)
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.token_entry.insert(0, self.config.get("TOKEN", ""))
        self.lockable["token"] = self.token_entry

        # BUTTONS (pod tokenem)       
        btn_frame = tk.Frame(root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(btn_frame, text="Socket:").pack(side=tk.LEFT, padx=(0, 2))
        self.conn_canvas = tk.Canvas(btn_frame, width=16, height=16, highlightthickness=0)
        self.conn_canvas.pack(side=tk.LEFT, padx=5)
        self.conn_dot = self.conn_canvas.create_oval(2, 2, 14, 14, fill="red")
        dispatcher.set_connection_callback(self.update_connection_led)

        ttk.Separator(btn_frame, orient='vertical').pack(side=tk.LEFT, padx=10, fill='y')
        ttk.Label(btn_frame, text="Watchers:").pack(side=tk.LEFT, padx=(0, 2))
        addW = tk.Button(btn_frame, text="Add Watcher", command=self.add_watcher)
        addW.pack(side="left", padx=5)
        saveBtn = tk.Button(btn_frame, text="Save Configuration", command=self.save_config)
        saveBtn.pack(side="left", padx=5)

        ttk.Separator(btn_frame, orient='horizontal').pack(side=tk.LEFT, padx=30, fill='y')  # Větší mezera před Run Bot
        ttk.Label(btn_frame, text="Bot Control:").pack(side=tk.LEFT, padx=(0, 2))
        run = tk.Button(btn_frame, text="Run Bot", command=self.run_bot)
        run.pack(side="left", padx=5)
        tk.Button(btn_frame, text="Quit Bot (q)", command=self.stop_bot).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Delete Messages (d)", command=self.safe_dispatch_clear).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Web Settings", command=self.open_web_settings).pack(side="right", padx=5)

        #ttk.Separator(btn_frame, orient='horizontal').pack(side=tk.RIGHT, padx=10)  # Větší mezera před Web Settings

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

        self.log_text = tk.Text(self.left_panel, state='disabled', wrap='word', bg="#E2E0E0", fg="#000000", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        log_scroll = ttk.Scrollbar(self.left_panel, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.bind("<MouseWheel>", lambda e: self.log_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # --- PRAVÁ STRANA (WATCHERY) ---
        self.right_panel = ttk.LabelFrame(self.main_frame, text="Watchers Configuration", padding="5")
        self.right_panel.grid(row=0, column=1, sticky="ns")

        # Seznam watcherů se scrollbarem
        self.canvas = tk.Canvas(self.right_panel, highlightthickness=0, width=600) # Pevnější šířka pro pravou stranu
        self.scrollbar = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)
        self.canvas.bind('<Enter>', lambda _: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind('<Leave>', lambda _: self.canvas.unbind_all("<MouseWheel>"))

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- GUI WATCHERS ---
        self.gui_frame = ttk.LabelFrame(self.root, text="GUI Watchers", padding="5")
        self.gui_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def gui_size(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = int(screen_width * 0.9)
        height = int(screen_height * 0.7)
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        
        self.root.state('zoomed')
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def append_log(self, text):
        # Bezpečný zápis do GUI z jakéhokoli vlákna
        self.root.after(0, self._actual_write, text)

    def _actual_write(self, text):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def update_connection_led(self, is_connected):
        """Změní barvu kolečka na základě stavu."""
        color = "green" if is_connected else "red"
        self.root.after(0, lambda: self.conn_canvas.itemconfig(self.conn_dot, fill=color))

    def open_web_settings(self):
        settings_win = WebSettingsWindow(self.root, self.config) 
        settings_win.main_app = self
        settings_win.transient(self.root)
        # target je settings_win, reference je self (hlavní GUI)
        settings_win.place_relative_to(self.root, position="nw", offset_x=50, offset_y=50)
        
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return {"TOKEN": "", "watchers": []}

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.logger.debug("Configuration loaded successfully.")

            clean = []
            for w in cfg.get("watchers", []):
                new_w = DEFAULT_WATCHER.copy()
                new_w.update(w)
                clean.append(new_w)

            cfg["watchers"] = clean
            if "web_layout" not in cfg:
                cfg["web_layout"] = DEFAULT_LAYOUT
            return cfg

        except json.JSONDecodeError:
            messagebox.showerror("Error", "config.json is corrupted. Creating a new one.")
            return {"TOKEN": "", "watchers": []}

    def render_watchers(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.lockable = {k: v for k, v in self.lockable.items() if not k.startswith("watcher_")}
        self.watcher_vars = []
        self.gui_watcher_list = []
        gui_id = 123450
        for idx, watcher in enumerate(self.config["watchers"]):
            self.watcher_vars.append({})
            if watcher.get("gui_watcher", False):
                watcher["channel_id"] = str(gui_id)
                self.gui_watcher_list.append((gui_id, watcher.get("comment", ""), idx))
                gui_id += 1
            self.render_one_watcher(self.scroll_frame, idx, watcher)
        self.render_gui_watchers()

    def render_gui_watchers(self):
        for w in self.gui_frame.winfo_children():
            w.destroy()
        self.gui_texts = {}
        self.gui_watcher_frames = {}
        for gui_id, comment, watcher_idx in self.gui_watcher_list:
            frame = ttk.LabelFrame(self.gui_frame, text=f"{gui_id}: {comment}")
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
            # Uložit referenci na frame a watcher_idx
            self.gui_watcher_frames[gui_id] = (frame, watcher_idx)
            
            # Textové pole
            text = tk.Text(frame, height=10, width=30, wrap='word')
            text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.gui_texts[gui_id] = text
            scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            scroll.pack(side=tk.RIGHT, fill="y")
            text.configure(yscrollcommand=scroll.set)
            
            # --- Logika pro Enter a Shift+Enter ---
            def handle_return(event, gid=gui_id):
                if not (event.state & 0x1):
                    self.send_gui_message(gid)
                    self.root.focus_set()
                    return "break" 
                return None

            text.bind("<Return>", handle_return)
            text.bind("<MouseWheel>", lambda e: text.yview_scroll(int(-1*(e.delta/120)), "units"))
            text.bind("<<Paste>>", lambda e, gid=gui_id: self.paste_image(gid))
            text.drop_target_register(tkdnd.DND_FILES)
            text.dnd_bind('<<DropEnter>>', lambda e: self.on_drop_enter(e))
            text.dnd_bind('<<Drop>>', lambda e, gid=gui_id: self.on_drop(e, gid))

            # Spodní rámec pro tlačítka
            bottom_frame = tk.Frame(frame)
            bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
            
            # Tlačítka
            btn_send = tk.Button(bottom_frame, text="Send", command=lambda id=gui_id: self.send_gui_message(id))
            btn_send.pack(side=tk.LEFT, padx=5)
            if self.config["watchers"][watcher_idx].get("image_panel") is not None:
                btn_file = tk.Button(bottom_frame, text="Attach File", command=lambda id=gui_id: self.select_file(id))
                btn_file.pack(side=tk.LEFT, padx=5)
            
    def select_file(self, gui_id):
        file_path = filedialog.askopenfilename(title="Select file to attach")
        if file_path:
            url = upload_image(file_path)
            if url:
                text_widget = self.gui_texts[gui_id]
                text_widget.insert(tk.END, f"\n{url}")
                self.logger.debug(f"File attached for {gui_id}: {url}")
            else:
                messagebox.showerror("Upload Error", "Failed to upload the file.")

    def paste_image(self, gui_id):
        try:
            img = ImageGrab.grabclipboard()
            if img:
                url = upload_image_from_pil(img)
                if url:
                    self.gui_texts[gui_id].insert(tk.END, f"\n{url}")
                    self.logger.debug(f"Image pasted for {gui_id}: {url}")
        except Exception as e:
            self.logger.debug(f"No image in clipboard or error: {e}")
    
    def on_drop_enter(self, event):
        """Handler pro drop enter - umožní drop."""
        event.widget.focus_force()
        return event.action

    def on_drop(self, event, gui_id):
        """Handler pro drop souborů."""
        self.logger.debug(f"Drop data: {event.data}")
        try:
            files = event.widget.tk.splitlist(event.data)  # Proper parsing for file lists
        except Exception as e:
            self.logger.error(f"Failed to parse drop data: {e}")
            files = []
        self.logger.debug(f"Parsed files: {files}")
        for file_path in files:
            file_path = file_path.strip()  # Remove any extra whitespace
            self.logger.debug(f"Processing file: {file_path}")
            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
                    url = upload_image(file_path)
                    if url:
                        text_widget = self.gui_texts[gui_id]
                        text_widget.insert(tk.END, f"\n{url}")
                        self.logger.debug(f"File dropped for {gui_id}: {url}")
                    else:
                        messagebox.showerror("Upload Error", f"Failed to upload {file_path}.")
                        self.logger.error(f"Failed to upload {file_path}.")
                else:
                    messagebox.showwarning("Unsupported File", f"File {file_path} is not a supported image type.")
                    self.logger.warning(f"Unsupported file type dropped: {file_path}")
            else:
                messagebox.showwarning("Invalid File", f"{file_path} is not a valid file.")
                self.logger.warning(f"Invalid file dropped: {file_path}")
            
    def toggle_watcher_visibility(self, var_enabled, details_frame):
            """Schová nebo zobrazí detaily watcheru."""
            if var_enabled.get():
                details_frame.pack(fill="x", padx=15, pady=5, after=details_frame.master.winfo_children()[0])
            else:
                details_frame.pack_forget()

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
        details_frame = ttk.LabelFrame(watcher_wrapper, text=f"Settings")

        # Checkbutton v hlavičce
        check = ttk.Checkbutton(
            header_frame, 
            text="ENABLED",
            variable=enabled_var,
            command=lambda: self.toggle_watcher_visibility(enabled_var, details_frame)
        )
        check.pack(side="left")

        # Poznámka v hlavičce 
        ttk.Label(header_frame, text=" | Comment:").pack(side="left")
        comment_entery = tk.StringVar(value=watcher.get("comment", ""))
        self.watcher_vars[idx]["comment"] = comment_entery
        ttk.Entry(header_frame, textvariable=comment_entery, width=40).pack(side="left", padx=5)
        # Zaregistruj callback pro aktualizaci GUI watcher label
        comment_entery.trace("w", lambda name, index, mode, idx=idx: self.update_gui_watcher_header(idx))

        # Tlačítko smazat v hlavičce
        tk.Button(header_frame, text="Remove", fg="red", command=lambda: self.remove_watcher(idx)).pack(side="right")
        
        # Channel ID
        row_id = ttk.Frame(details_frame)
        row_id.pack(fill="x", padx=5, pady=2)
        ttk.Label(row_id, text="Channel ID:", width=10).pack(side="left")
        var_cid = tk.StringVar(value=watcher.get("channel_id", ""))
        self.watcher_vars[idx]["channel_id"] = var_cid
        ttk.Entry(row_id, textvariable=var_cid, width=20).pack(side="left", expand=True, padx=5)
        # File Path 
        ttk.Label(row_id, text="Output File:", width=10).pack(side="left", padx=(10,0))
        var_path = tk.StringVar(value=watcher.get("file_path", "temp/output"))
        self.watcher_vars[idx]["file_path"] = var_path
        ttk.Entry(row_id, textvariable=var_path, width=20).pack(side="left", expand=True, padx=5)
        #GUI watcher
        var_gui = tk.BooleanVar(value=watcher.get("gui_watcher", False))
        self.watcher_vars[idx]["gui_watcher"] = var_gui
        ttk.Checkbutton(row_id, text="GUI Watcher", variable=var_gui, command=lambda idx=idx, var=var_gui: self.update_gui_watcher(idx, var)).pack(side="left", padx=5)

        #interval, rows per column, column width
        row_limits = ttk.Frame(details_frame)
        row_limits.pack(fill="x", padx=5, pady=2)
        #interval
        ttk.Label(row_limits, text="Interval (s):").pack(side="left")
        var_interval = tk.IntVar(value=watcher.get("interval", 10))
        self.watcher_vars[idx]["interval"] = var_interval
        ttk.Spinbox(row_limits, from_=1, to=300, textvariable=var_interval, width=5).pack(side="left", padx=5)        
        # Manual Clear
        var_clear = tk.BooleanVar(value=watcher.get("manual_clear", False))
        self.watcher_vars[idx]["manual_clear"] = var_clear
        ttk.Checkbutton(row_limits, text="Manual Clear", variable=var_clear).pack(side="left", padx=5)
    
        # Ignore Mode & Show Author
        row_modes = ttk.Frame(details_frame)
        row_modes.pack(fill="x", padx=5, pady=2)
        # Ignore Mode
        ttk.Label(row_modes, text="Ignore Mode:").pack(side="left")
        var_ignore = tk.StringVar(value=str(watcher.get("ignore_mode", "None")))
        self.watcher_vars[idx]["ignore_mode"] = var_ignore
        ignore_combo = ttk.Combobox(row_modes, textvariable=var_ignore, values=["None", "bot", "human"], width=10)
        ignore_combo.pack(side="left", padx=5)
        # Show Author
        ttk.Label(row_modes, text="Show Author:").pack(side="left", padx=(10,0))
        var_show_author = tk.StringVar(value=str(watcher.get("show_author_mode", "both")))
        self.watcher_vars[idx]["show_author"] = var_show_author
        author_combo = ttk.Combobox(row_modes, textvariable=var_show_author, values=["both", "human", "bot", "None"], width=10)
        author_combo.pack(side="left", padx=5)
        # Output file
        ttk.Label(row_modes, text="Type Output:").pack(side="left", padx=(10,0))
        var_type_output = tk.StringVar(value=watcher.get("type_output", "socket"))
        self.watcher_vars[idx]["type_output"] = var_type_output
        type_combo = ttk.Combobox(row_modes, textvariable=var_type_output, values=["socket", "txt", "both"], width=10)
        type_combo.pack(side="left", padx=5)

        # Header Text
        row_header = ttk.Frame(details_frame)
        row_header.pack(fill="x", padx=5, pady=2)
        ttk.Label(row_header, text="Header Text:").pack(side="left")
        var_header = tk.StringVar(value=watcher.get("header_text", ""))
        self.watcher_vars[idx]["header_text"] = var_header
        ttk.Entry(row_header, textvariable=var_header, width=20).pack(side="left", padx=5)
        # Text panel
        ttk.Label(row_header, text="Text Panel:").pack(side="left", padx=(10,0))
        var_panel = tk.StringVar(value=str(watcher.get("socket_panel", "panel-a")))
        self.watcher_vars[idx]["socket_panel"] = var_panel
        panel_combo = ttk.Combobox(row_header, textvariable=var_panel, values=["panel-a", "panel-b", "panel-c", "panel-d","panel-e", "panel-o", "None"], width=10)
        panel_combo.pack(side="left", padx=5)
        # Image panel
        ttk.Label(row_header, text="Image panel:").pack(side="left", padx=(10,0))
        var_image_panel = tk.StringVar(value=str(watcher.get("image_panel", "panel-o")))
        self.watcher_vars[idx]["image_panel"] = var_image_panel
        image_combo = ttk.Combobox(row_header, textvariable=var_image_panel, values=["panel-o", "None"], width=10)
        image_combo.pack(side="left", padx=5)

        # 3. REGISTRACE DO LOCKABLE
        self.lockable[f"watcher_{idx}"] = watcher_wrapper
        # 4. NASTAVENÍ POČÁTEČNÍ VIDITELNOSTI
        self.toggle_watcher_visibility(enabled_var, details_frame)
        
    def add_watcher(self):
        self.config["watchers"].append(DEFAULT_WATCHER.copy())
        self.render_watchers()

    def remove_watcher(self, idx):
        del self.config["watchers"][idx]
        self.render_watchers()

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
                    "file_path": get_str("file_path", "temp/output"),
                    "socket_panel": get_combo("socket_panel", "panel-a"),
                    "image_panel": get_combo("image_panel", "panel-o"),
                    "interval": get_int("interval", 10),
                    "show_author_mode": get_combo("show_author", "both"),
                    "ignore_mode": get_combo("ignore_mode", None),
                    "manual_clear": get_bool("manual_clear", False),
                    "type_output": get_combo("type_output", "socket"),
                    "header_text": get_str("header_text", ""),
                    "gui_watcher": get_bool("gui_watcher", False),
                }
                clean_watchers.append(clean)
            self.config["watchers"] = clean_watchers
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.info("Configuration saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    def run_bot(self):
        if self.bot_running:
            self.logger.warning("Bot already running.")
            return

        self.save_config()
        dispatcher.config = self.config

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
        
    def stop_bot(self, wait_secs: float = 1.0):
        if not self.bot_running:
            self.logger.warning("Bot is not running.")
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

    def on_key_press(self, event):
        """Handler pro stisk klávesy v GUI okně."""
        focus = self.root.focus_get()
        if not isinstance(focus, (tk.Entry, tk.Text)):
            key = event.char.lower()
            if self.bot_running:
                if key == 'q':
                    self.stop_bot()
                else:
                    asyncio.run_coroutine_threadsafe(dispatcher.on_key_press(key), self.loop)

    def safe_dispatch_clear(self):
        """ Volá manuální mazání přes dispatcher na všech watcherech, kde je to povoleno. """
        if self.bot_running and self.loop:
            asyncio.run_coroutine_threadsafe(dispatcher.dispatch_clear(), self.loop)
        else:
            self.logger.warning("Bot not running, cannot dispatch clear.")

    def update_gui_watcher_header(self, idx):
        """Aktualizuje záhlaví GUI watcher textového pole když se změní comment."""
        try:
            # Najdi odpovídající gui_id pro tento watcher
            for gui_id, comment, watcher_idx in self.gui_watcher_list:
                if watcher_idx == idx:
                    # Získej new comment z StringVar
                    new_comment = self.watcher_vars[idx].get("comment", tk.StringVar()).get()
                    # Aktualizuj text LabelFrame
                    if gui_id in self.gui_watcher_frames:
                        frame, _ = self.gui_watcher_frames[gui_id]
                        frame.configure(text=f"{gui_id}: {new_comment}")
                    break
        except Exception as e:
            self.logger.error(f"Error updating GUI watcher header: {e}")

    def update_gui_watcher(self, idx, var):
        self.config["watchers"][idx]["gui_watcher"] = var.get()
        self.render_watchers()

    def send_gui_message(self, gui_id):
        text = self.gui_texts[gui_id].get("1.0", tk.END).strip()
        if text:
            self.safe_dispatch_manual(str(gui_id), text, "GUI")
            self.gui_texts[gui_id].delete("1.0", tk.END)

    def safe_dispatch_manual(self, target_id, text, author):
        if self.bot_running and self.loop:
            asyncio.run_coroutine_threadsafe(dispatcher.dispatch_manual(target_id, text, author), self.loop)
        else:
            self.logger.warning("Bot not running, cannot dispatch manual message.")

    def on_close(self):
        if self.bot_running:
            self.stop_bot()
        
        self.logging_ctx.__exit__(None, None, None) # Vypnutí loggeru
        self.root.destroy()
        sys.exit(0)

class WebSettingsWindow(tk.Toplevel, FocusManager, WindowPositionMixIn):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.withdraw()  # Skryje okno během inicializace
        self.setup_focus_management()
        self.transient(parent)
        self.main_app = None

        self.logging_ctx = Logging()
        self.logger = setup_logger("Web Settings", level=logging.DEBUG)

        self.title("Web Layout Editor & Layer Manager")
        #self.geometry("1100x750")
        self.config_data = config
        self.layout_cfg = config.get("web_layout", {})
        
        # Měřítko pro zobrazení
        self.scale = 0.3
        self.canvas_w = int(self.layout_cfg["canvas"]["width"] * self.scale)
        self.canvas_h = int(self.layout_cfg["canvas"]["height"] * self.scale)
        
        self.active_panel_id = None
        self.selected_pannels = None
        self._drag_data = {"x": 0, "y": 0, "item": None}
        self.bg_image_tk = None # Reference pro GC

        self.manual_select = True
        
        self.setup_ui()
        self.load_bg_from_config() # Automatické načtení
        self.refresh_layer_table()
        self.draw_panels()

    def setup_ui(self):
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # LEVÁ STRANA - CANVAS
        self.left_frame = ttk.Frame(self.paned)
        self.canvas = tk.Canvas(
            self.left_frame, width=self.canvas_w, height=self.canvas_h, 
            bg="#1a1a1a", highlightthickness=2, highlightbackground="#444444"
        )
        self.canvas.pack(pady=5)
        
        # Bindování myši
        self.canvas.bind("<ButtonPress-1>", self.on_start_drag)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_stop_drag)
        
        self.paned.add(self.left_frame, weight=3)

        # Tlačítka pro ukládání a aplikaci
        action_frame = ttk.Frame(self.left_frame, padding=5)
        action_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
        
        ttk.Button(action_frame, text="Change Background", command=self.change_bg).pack(side=tk.LEFT, expand=True, fill=tk.X, pady=2)
        ttk.Button(action_frame, text="Apply to OBS", command=self.apply_to_obs).pack(side=tk.LEFT, expand=True, fill=tk.X, pady=2)
        ttk.Button(action_frame, text="Save & Close", command=self.apply_and_close, style="Accent.TButton").pack(side=tk.LEFT, expand=True, fill=tk.X, pady=2)

        # PRAVÁ STRANA - CONTROL
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=2)

        # Tabulka vrstev
        ttk.Label(self.right_frame, text="Panels:").pack(anchor="w")
        tree_container = ttk.Frame(self.right_frame)
        tree_container.pack(fill=tk.BOTH, expand=True, pady=5)
        num_panels = len(self.layout_cfg.get("panels", {}))
        tree_height = min(max(2, num_panels), 10)
        self.tree = ttk.Treeview(tree_container, columns=("name", "z", "type", "x", "y", "width", "height", "column", "auto_size"), show="headings", height=tree_height)
        self.tree.heading("name", text="Panel Name")
        self.tree.heading("z", text="Z")
        self.tree.heading("type", text="Type")
        self.tree.heading("x", text="X")
        self.tree.heading("y", text="Y")
        self.tree.heading("width", text="Width")
        self.tree.heading("height", text="Height")
        self.tree.heading("column", text="Col W")
        self.tree.heading("auto_size", text="Auto-size")
        self.tree.column("name", width=80, anchor="center")
        self.tree.column("z", width=30, anchor="center")
        self.tree.column("type", width=50, anchor="center")
        self.tree.column("x", width=50, anchor="center")
        self.tree.column("y", width=50, anchor="center")
        self.tree.column("width", width=60, anchor="center")
        self.tree.column("height", width=60, anchor="center")
        self.tree.column("column", width=60, anchor="center")
        self.tree.column("auto_size", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.get_val_selected)
        self.tree.bind("<Double-1>", self.toggle_panel_type)

        z_frame = ttk.Frame(self.right_frame)
        z_frame.pack(fill=tk.X, pady=5)
        ttk.Button(z_frame, text="▲ Move Up", command=lambda: self.set_val_change_z(1)).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(z_frame, text="▼ Move Down", command=lambda: self.set_val_change_z(-1)).pack(side=tk.LEFT, expand=True, fill=tk.X)

        prop_frame = ttk.LabelFrame(self.right_frame, text="Panel Geometry (px)", padding=10)
        prop_frame.pack(fill=tk.NONE, pady=5, anchor="center")

        self.vars = {
            "x": tk.IntVar(), "y": tk.IntVar(),
            "width": tk.IntVar(), "height": tk.IntVar(),
            "z_index" : tk.IntVar(), "auto_size": tk.BooleanVar(value=True),
            "column_width": tk.IntVar()
        }

        # První řádek: X, Y, Z-Index
        row1 = ttk.Frame(prop_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="X:", width=8).pack(side=tk.LEFT)
        x_spin = ttk.Spinbox(row1, width=8, from_=0, to=10000, textvariable=self.vars['x'])
        x_spin.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row1, text="Y:", width=8).pack(side=tk.LEFT)
        y_spin = ttk.Spinbox(row1, width=8, from_=0, to=10000, textvariable=self.vars['y'])
        y_spin.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row1, text="Z-Index:", width=10).pack(side=tk.LEFT)
        z_spin = ttk.Spinbox(row1, textvariable=self.vars['z_index'], width=8, from_=-1000, to=1000)
        z_spin.pack(side=tk.LEFT)

        # Druhý řádek: Width, Height, Column Width
        row2 = ttk.Frame(prop_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Width:", width=8).pack(side=tk.LEFT)
        width_spin = ttk.Spinbox(row2, width=8, from_=0, to=10000, textvariable=self.vars['width'])
        width_spin.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row2, text="Height:", width=8).pack(side=tk.LEFT)
        height_spin = ttk.Spinbox(row2, width=8, from_=0, to=10000, textvariable=self.vars['height'])
        height_spin.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row2, text="Col Width:", width=10).pack(side=tk.LEFT)
        column_width_spin = ttk.Spinbox(row2, textvariable=self.vars['column_width'], width=8, from_=0, to=1000)
        column_width_spin.pack(side=tk.LEFT)

        # Třetí řádek: Auto-size
        row3 = ttk.Frame(prop_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(row3, text="Auto-size (Content)", variable=self.vars['auto_size']).pack(side=tk.LEFT)

       
        for children in prop_frame.winfo_children():
            for child in children.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.bind("<Return>", lambda e: self.set_val_active_panel())
                    child.bind("<FocusOut>", lambda e: self.set_val_active_panel())


        ttk.Button(self.right_frame, text="Open Font & Style Editor", 
                   command=self.open_style_editor).pack(fill=tk.X, pady=10)

    def load_bg_from_config(self):
        """Načte obrázek cesty uložené v JSONu."""
        path = self.layout_cfg["canvas"].get("bg_preview", "")
        if path and os.path.exists(path):
            try:
                img = Image.open(path)
                img = img.resize((self.canvas_w, self.canvas_h), Image.Resampling.LANCZOS)
                self.bg_image_tk = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor="nw", image=self.bg_image_tk, tags="bg_img")
                self.canvas.tag_lower("bg_img")
            except Exception as e:
                print(f"Error loading bg: {e}")

    def change_bg(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if path:
            self.layout_cfg["canvas"]["bg_preview"] = path
            self.load_bg_from_config()

    def refresh_layer_table(self):

        for i in self.tree.get_children(): self.tree.delete(i)
        
        panels = self.layout_cfg.get("panels", {})
        # Seřadíme podle Z-indexu sestupně, aby vrchní byly v tabulce nahoře
        sorted_panels = sorted(panels.items(), key=lambda x: x[1].get("z_index", 0), reverse=True)
        
        for p_id, info in sorted_panels:
            panel_type = "Image" if info.get("is_image", False) else "Text"
            self.tree.insert("", tk.END, iid=p_id, values=(p_id, info.get("z_index", 0), panel_type, info.get("x", 0), info.get("y", 0), info.get("width", 0), info.get("height", 0), info.get("column_width", 0), "Yes" if info.get("auto_size", False) else "No"))
            
        new_hight = min(max(2, len(panels)), 12)
        self.tree.configure(height=new_hight)
        self.right_frame.update_idletasks()
        
        self.manual_select = False
        if self.active_panel_id and self.tree.exists(self.active_panel_id):
            self.tree.selection_set(self.active_panel_id)
        if self.selected_pannels:
            for p_id in self.selected_pannels:
                if self.tree.exists(p_id):
                    self.tree.selection_add(p_id)
        self.tree.update()
        self.manual_select = True
        
    def draw_panels(self):
        self.canvas.delete("panel")
        # Kreslíme od nejnižšího Z-indexu po nejvyšší
        panels = self.layout_cfg.get("panels", {})
        global_style = self.layout_cfg.get("global_style", {})
        sorted_keys = sorted(panels.keys(), key=lambda k: panels[k].get("z_index", 0))
        self.active_overlay_img = None # Resetujeme overlay pro aktivní panel

        if self.active_panel_id and self.active_panel_id in sorted_keys:
            sorted_keys.remove(self.active_panel_id)
            sorted_keys.append(self.active_panel_id)
        
        for p_id in sorted_keys:
            p_info = panels[p_id]
            is_active = (p_id == self.active_panel_id)
            is_auto = p_info.get("auto_size", False)
            text_color = p_info.get("text_color", "#FFFFFF")
            center_content = p_info.get("center_content", False)
            is_image_panel = p_info.get("is_image", False)
            
            x, y = p_info["x"] * self.scale, p_info["y"] * self.scale
            w = int(p_info.get("width", 350) * self.scale) 
            h = int(p_info.get("height", 100) * self.scale) 

            outline_color = "white" if is_active else ("#7AD896" if is_image_panel else "#A8A8A8")
            dash_style = (5, 2) if is_auto else None

            if is_active:
                overlay_auto = Image.new('RGBA', (max(1, w), max(1, h)), (0, 120, 215, 150))
                overlay = Image.new('RGBA', (max(1, w), max(1, h)), (0, 120, 215, 230))
                overlay_image_panel = Image.new('RGBA', (max(1, w), max(1, h)), (83, 136, 99, 230))
                self.active_overlay_img = ImageTk.PhotoImage(overlay_auto) if is_auto else ImageTk.PhotoImage(overlay_image_panel if is_image_panel else overlay)
                self.canvas.create_image(x, y, image=self.active_overlay_img, anchor="nw", tags=("panel", p_id))

                cw_val = p_info.get("column_width", 0)
                if cw_val > 0: 
                    cw_scaled = int(cw_val * self.scale)
                    self.canvas.create_rectangle(x, y, x+cw_scaled, y+h, outline="#FFD700",width=1, dash=(2,2), tags=("panel", p_id, "column_width"))           
        
            self.canvas.create_rectangle(x, y, x+w, y+h, fill= "", outline=outline_color, width=2 if is_active else 1, tags=("panel", p_id), dash=dash_style)
            if center_content:
                text_anchor = "center"
                text_x, text_y = x + w/2, y + h/2
            else:
                text_anchor = "nw"
                text_x, text_y = x + 5, y + 5

            text_offset = p_info.get("z_index", 0)
            text_x += (text_offset-1) * 20 if text_offset > 1 else 0

            if not text_color:
                text_color =  global_style.get("text_color", "#FFFFFF") 
            label_text = f"{p_id} [AUTO]" if is_auto else (f"{p_id} [IMAGE]" if is_image_panel else p_id)
            self.canvas.create_text(text_x, text_y, text=label_text, anchor=text_anchor, fill=text_color, tags=("panel", p_id))
        
        self.canvas.tag_lower("bg_img")

    def get_val_selected(self, event):
        if not self.manual_select:
            return
        selected = self.tree.selection()
        self.z_axes = [] # Resetujeme z-axes pro více výběrů
        if len(selected) == 1 and selected[0] == self.active_panel_id:
            self.tree.selection_remove(selected[0])
            self.active_panel_id = None
        elif len(selected) > 1 and self.selected_pannels and set(selected) == set(self.selected_pannels):
            for p_id in selected:
                self.tree.selection_remove(p_id)
            self.selected_pannels = None
        elif len(selected) > 1:
            self.active_panel_id = None
            self.selected_pannels = selected
            for p_id in selected:
                self.z_axes.append(self.layout_cfg["panels"][p_id].get("z_index", 0))
        elif selected:
            self.active_panel_id = selected[0]
            self.selected_pannels = None
            p = self.layout_cfg["panels"][self.active_panel_id]
            self.vars["x"].set(p["x"])
            self.vars["y"].set(p["y"])
            self.vars["width"].set(p.get("width", 200)) # Default 200
            self.vars["height"].set(p.get("height", 100)) # Default 100
            self.vars["z_index"].set(p.get("z_index", 0))
            self.vars["auto_size"].set(p.get("auto_size", False))
            cw = p.get("column_width", 0) 
            self.vars["column_width"].set(cw if cw is not None else 0)
        self.draw_panels()
        
    def set_val_change_z(self, delta):
        if self.active_panel_id and not self.selected_pannels:
            p = self.layout_cfg["panels"][self.active_panel_id]
            # Změníme hodnotu přímo v slovníku layout_cfg
            p["z_index"] = p.get("z_index", 0) + delta
            self.refresh_layer_table()
            self.draw_panels()
        elif self.selected_pannels:
            for p_id in self.selected_pannels:
                p = self.layout_cfg["panels"][p_id]
                p["z_index"] = p.get("z_index", 0) + delta
            self.refresh_layer_table()
            self.draw_panels()

    def set_val_active_panel(self, event=None):
        if self.active_panel_id:
            p = self.layout_cfg["panels"][self.active_panel_id]
            try:                # Ověření, že všechny hodnoty jsou platné
                p["x"] = self.vars["x"].get()
                p["y"] = self.vars["y"].get()
                p["width"] = self.vars["width"].get()
                p["height"] = self.vars["height"].get()
                p["z_index"] = self.vars["z_index"].get()
                p["auto_size"] = self.vars["auto_size"].get()
                try:
                    cw = self.vars["column_width"].get()
                    if cw > 0:
                        p["column_width"] = cw
                    else:
                        p.pop("column_width", None)
                except:
                    p.pop("column_width", None)
            except tk.TclError:
                return
            self.draw_panels()
            self.refresh_layer_table()

    def toggle_panel_type(self, event):
        selected = self.tree.selection()
        if selected:
            p_id = selected[0]
            p_info = self.layout_cfg["panels"][p_id]
            if p_info.get("is_image", False):
                p_info["is_image"] = False
                p_info.pop("img_fit", None)
            else:
                p_info["is_image"] = True
                p_info["img_fit"] = "cover"
            self.refresh_layer_table()
            self.draw_panels()

    def on_start_drag(self, event):
        if not self.active_panel_id: return
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        if any(self.active_panel_id in self.canvas.gettags(i) for i in items):
            self._drag_data.update({"item": self.active_panel_id, "x": event.x, "y": event.y})

    def on_drag(self, event):
        if self._drag_data["item"]:
            dx, dy = event.x - self._drag_data["x"], event.y - self._drag_data["y"]
            self.canvas.move(self._drag_data["item"], dx, dy)
            self._drag_data.update({"x": event.x, "y": event.y})
            # Update políček v reálném čase
            bbox = self.canvas.bbox(self._drag_data["item"])
            if bbox:
                self.vars["x"].set(int(bbox[0] / self.scale))
                self.vars["y"].set(int(bbox[1] / self.scale))

    def on_stop_drag(self, event):
        if self._drag_data["item"]:
            self.set_val_active_panel()
            self._drag_data["item"] = None

    def open_style_editor(self):
        style_win = StyleEditorWindow(self, self.layout_cfg, self.apply_to_obs, self.draw_panels)
        style_win.main_app = self.main_app
        style_win.transient(self)
        style_win.place_relative_to(self, position="nw", offset_x=20, offset_y=20)

    def apply_to_obs(self):
        # Kontrola, zda bot vůbec běží přes main_client.engine
       
        self.config_data["web_layout"] = self.layout_cfg
        try:
            if dispatcher.loop and dispatcher.loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        sio.emit("init_layout", self.layout_cfg), 
                        dispatcher.loop
                    )
                except Exception as e:
                    self.logger.error(f"Error sending to OBS: {e}")
            else:
                messagebox.showwarning(
                    "Bot Not Running", 
                    "Layout could not be sent to OBS. Start the bot to update the live overlay."
                )
        except Exception as e:
            # Zachytíme případné jiné chyby, aby aplikace nespadla
            self.logger.error(f"Silent error in apply_to_obs: {e}")

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config.json: {e}")

    def apply_and_close(self):
        self.apply_to_obs() # Poslat do OBS před zavřením
        self.destroy()
        
class StyleEditorWindow(tk.Toplevel, FocusManager, WindowPositionMixIn):
    def __init__(self, parent, layout_cfg, on_save_callback, on_update_callback):
        super().__init__(parent)
        self.withdraw()
        self.setup_focus_management()
        self.title("Font & Style Editor")
        
        # Geometrii nenastavujeme fixně, necháme ji dýchat
        self.transient(parent)
        
        self.layout_cfg = layout_cfg
        self.on_save_callback = on_save_callback
        self.on_update_callback = on_update_callback
        self.cached_fonts, self.max_font_width = self.get_system_fonts()

        # Kontejner
        self.main_container = ttk.Frame(self)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Spodní lišta s tlačítkem (vytvořena dřív, aby byla "přibitá" dolů)
        self.bottom_bar = ttk.Frame(self)
        self.bottom_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=10)


        self.apply_and_close_btn = ttk.Button(self.bottom_bar, text="Apply & Close", command=self.apply_and_close)
        self.apply_and_close_btn.pack(side=tk.RIGHT)
        self.apply_btn = ttk.Button(self.bottom_bar, text="Apply", command=self.apply)
        self.apply_btn.pack(side=tk.RIGHT)
        ttk.Label(self.bottom_bar, text="💡 Changes saved by leave edit file or enter key. Zero in text size is ignored.").pack(side=tk.LEFT)

        # Scrollable Canvas
        self.canvas_frame = ttk.Frame(self.main_container)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(self.canvas_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scroll_content = ttk.Frame(self.canvas)

        self.scroll_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.setup_table()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def setup_table(self):
        panels = self.layout_cfg.get("panels", {})
        text_panels = ["global"] + [pid for pid, info in panels.items() if not info.get("is_image", False)]
        image_panels = [pid for pid, info in panels.items() if info.get("is_image", False)]
        headers_text = ["ID", "Font Family", "Size", "Center", "Bg color", "Text Color", "<b> Color", "<b> Size", "<i> Color", "<i> Size", "<u> Color", "<u> Size", "<s> Color", "<s> Size"]
        headers_image = ["ID", "Bg color","Center", "Img Fit", "Opacity"]
        mapping_text = [
                ("font_family", "font_combo"), ("font_size", "number"), 
                ("center_content", "bool"),
                ("bg_color", "bg_color"),
                ("text_color", "color"),
                ("b_color", "color"), ("b_size", "number"),
                ("i_color", "color"), ("i_size", "number"), 
                ("u_color", "color"), ("u_size", "number"), 
                ("s_color", "color"), ("s_size", "number")
            ]
        mapping_image = [
                ("bg_color", "bg_color"), ("center_content", "bool"), ("img_fit", "combo_fit"), ("img_opacity", "float"),
            ]

        #row_ids = ["global"] + list(self.layout_cfg.get("panels", {}).keys())

        def draw_section(parent, title, row_ids, mapping, headers):
            frame = ttk.LabelFrame(parent, text=title, padding=10)
            frame.pack(fill=tk.X, pady=(10,0), padx=5)

            for col, text in enumerate(headers):
                lbl = tk.Label(frame, text=text, font=("Arial", 9, "bold"), 
                            padx=10, pady=5, relief="flat", bg="#e1e1e1")
                lbl.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

            for r_idx, rid in enumerate(row_ids, start=1):
                tk.Label(frame, text=rid.upper(), padx=10, font=("Arial", 9, "bold")).grid(row=r_idx, column=0, sticky="w")
                is_auto = False
                if rid != "global":
                    is_auto = self.layout_cfg.get("panels", {}).get(rid, {}).get("auto_size", False)

                for c_idx, (key, field_type) in enumerate(mapping, start=1):
                    val = self.get_val(rid, key)
                    if field_type == "text":
                        ent = ttk.Entry(frame, width=8)
                        ent.insert(0, str(val))
                        ent.grid(row=r_idx, column=c_idx, padx=3, pady=3, )
                        ent.bind("<FocusOut>", lambda e, r=rid, k=key, w=ent: self.set_val(r, k, w.get()))
                    
                    elif field_type == "float":
                        spin = ttk.Spinbox(frame, width=8, from_=0.00, to=1.00, increment=0.01)
                        try:
                            spin.set(float(val) if val is not None else 1.00)
                        except ValueError:
                            spin.set(1.00)
                        spin.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        spin.bind("<FocusOut>", lambda e, r=rid, k=key, w=spin: self.set_val(r, k, w.get()))
                        spin.bind("<Return>", lambda e, r=rid, k=key, s=spin: self.set_val(r, k, s.get()))

                    elif field_type == "number":
                        spin = ttk.Spinbox(frame, width=8, from_=0, to=10000)
                        spin.set(val if val is not None else 0)
                        spin.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        spin.bind("<FocusOut>", lambda e, r=rid, k=key, w=spin: self.set_val(r, k, w.get()))
                        spin.bind("<Return>", lambda e, r=rid, k=key, s=spin: self.set_val(r, k, s.get()))

                    elif field_type == "bool":
                        # Checkbox pro centrování
                        var = tk.BooleanVar(value=True if str(val).lower() == "true" else False)
                        cb = ttk.Checkbutton(frame, variable=var, 
                                            command=lambda r=rid, k=key, v=var: self.set_val(r, k, v.get()))
                        cb.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        
                        # Logika: Pokud je to auto-size panel, centrování zakážeme
                        if is_auto or rid == "global":
                            cb.state(['disabled'])
                            self.set_val(rid, key, False) # Vynutit vypnutí v datech

                    elif field_type == "combo_fit":
                        #var = tk.StringVar(str(value=val) if val else "")
                        combo = ttk.Combobox(frame, values=["", "cover", "contain", "fill"], width=8, state="readonly")
                        combo.set(str(val) if str(val) else "")
                        combo.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        combo.bind("<<ComboboxSelected>>", lambda e, r=rid, k=key, c=combo: self.set_val(r, k, c.get()))
                        if rid == "global":
                            combo.state(['disabled'])
                            self.set_val(rid, key, "") # Vynutit "" pro global

                    elif field_type == "font_combo":
                        fonts = self.cached_fonts
                        s = ttk.Style()
                        s.configure("Wide.TCombobox", postoffset=(0, 0, self.max_font_width, 0))
                        combo = ttk.Combobox(frame, values=fonts, width=15, style="Wide.TCombobox", state="readonly")
                        current_val = str(val)
                        found_match = [f for f in fonts if f.startswith(current_val)]
                        combo.set(found_match[0] if found_match else current_val)
                        combo.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        combo.bind("<<ComboboxSelected>>", lambda e, r=rid, k=key, c=combo: self.set_val(r, k, c.get().split(" [")[0]))
                        #combo.bind("<FocusOut>", lambda e, r=rid, k=key, c=combo: self.set_val(r, k, c.get().split(" [")[0]))
                    

                    elif field_type in ["color", "bg_color"]:
                        cell = ttk.Frame(frame)
                        cell.grid(row=r_idx, column=c_idx, padx=3, pady=3)
                        c_ent = ttk.Entry(cell, width=8)
                        c_ent.insert(0, str(val))
                        c_ent.grid(row=0, column=0)
                        btn = tk.Button(cell, bg=val if str(val).startswith("#") else "white", 
                                    width=2, height=1, relief="flat", command=lambda r=rid, k=key, e=c_ent: self.pick_color(r, k, e))
                        btn.grid(row=0, column=1, padx=2)
                        if field_type == "bg_color":
                            op_key = key + "_opacity"
                            op_val = self.get_val(rid, op_key)

                            try:
                                op_val = float(op_val) if op_val not in [None, ""] else 1.0
                            except:
                                op_val = 1.0
                            row_var = tk.DoubleVar(value=op_val)

                            scale = tk.Scale(cell, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL,
                                            showvalue=True, length=60, font=("Arial", 7),
                                            highlightthickness=0, troughcolor="#cccccc", sliderrelief="flat",
                                            variable=row_var,
                                            command=lambda v, r=rid, k=op_key: self.set_val(r, k, v))
                            scale.set(op_val)
                            scale.grid(row=1, column=0, columnspan=2, sticky="we")
                        c_ent.bind("<FocusOut>", lambda e, r=rid, k=key, w=c_ent, p=btn: self.update_from_entry(r, k, w, p))
                        c_ent.bind("<Return>", lambda e, r=rid, k=key, w=c_ent, p=btn: self.update_from_entry(r, k, w, p))
                    #pass
        if text_panels:
            draw_section(self.scroll_content, "Text Panels", text_panels, mapping_text, headers_text)
        if image_panels:
            draw_section(self.scroll_content, "Image Panels", image_panels, mapping_image, headers_image)

        # FINÁLNÍ KROK: Přizpůsobení okna
        self.scroll_content.update_idletasks()
        w = self.scroll_content.winfo_reqwidth() + 50
        h = self.scroll_content.winfo_reqheight() + 100
        # Omezíme maximální velikost na 90% obrazovky, aby okno nezmizelo
        max_h = int(self.winfo_screenheight() * 0.8)
        self.canvas.configure(width=w, height=min(h-100, max_h))

    def get_val(self, rid, key):
        if rid == "global": return self.layout_cfg.get("global_style", {}).get(key, "")
        return self.layout_cfg.get("panels", {}).get(rid, {}).get(key, "")

    def set_val(self, rid, key, val):
        ignore_values = ["", None]
        if isinstance(val, bool):
            clean_val = val
        else:
            clean_val = str(val).strip()

        if not isinstance(clean_val, bool) and clean_val not in ignore_values:
            try:
                #isdigit() nebere záporná čísla, proto tato kontrola:
                if clean_val.lstrip('-').isdigit():
                    clean_val = int(clean_val)
            except ValueError:
                pass
        if not key.endswith("_opacity"):
            ignore_values.extend([0, "0"])

        if rid == "global":
            if "global_style" not in self.layout_cfg: 
                self.layout_cfg["global_style"] = {}
            self.layout_cfg["global_style"][key] = clean_val
        else:
            if rid in self.layout_cfg.get("panels", {}):
                if key.endswith("_opacity"):
                    color_key = "bg_color" 
                    if color_key in self.layout_cfg["panels"][rid] and clean_val != "":
                        self.layout_cfg["panels"][rid][key] = clean_val
                    elif key in self.layout_cfg["panels"][rid]:
                        del self.layout_cfg["panels"][rid][key]
                if clean_val in ignore_values or (isinstance(clean_val, bool) and clean_val is False):
                    # Pokud je hodnota prázdná, smažeme klíč z panelu
                    if key in self.layout_cfg["panels"][rid]:
                        del self.layout_cfg["panels"][rid][key]
                else:
                    # Jinak hodnotu normálně uložíme
                    self.layout_cfg["panels"][rid][key] = clean_val

    def pick_color(self, rid, key, entry_widget):
        current = entry_widget.get()
        color = colorchooser.askcolor(initialcolor=current if current.startswith("#") else "#ffffff")[1]
        if color:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, color)
            self.set_val(rid, key, color)
            for child in entry_widget.master.winfo_children():
                if isinstance(child, tk.Button): child.configure(bg=color)

    def update_from_entry(self, rid, key, entry_widget, preview_widget):
        val = entry_widget.get()
        self.set_val(rid, key, val)
        if val.startswith("#") and len(val) == 7: preview_widget.configure(bg=val)

    def get_system_fonts(self):
        """Vrátí seznam fontů s označením, zda jsou neproporcionální."""
        all_fonts = sorted(list(set(font.families())))
        font_list = [""]
        max_width = 0
        measure_font = font.Font(size=5)
        
        for f in all_fonts:
            if f.startswith("@"): continue # Přeskočíme vertikální asijské fonty
            
            test_font = font.Font(family=f, size=10)
            is_mono = test_font.measure("i") == test_font.measure("M")
            
            suffix = " [Mono]" if is_mono else ""
            full_name = f"{f}{suffix}"
            font_list.append(full_name)
            max_width = max(max_width, measure_font.measure(full_name))
            
        return font_list, max_width

    def apply(self):
        self.on_save_callback()
        self.on_update_callback()    
    
    def apply_and_close(self):
        self.on_save_callback()
        self.on_update_callback()
        self.destroy()

root = tkdnd.Tk()
ConfigGUI(root)
root.mainloop()
