#config_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import subprocess
import threading
import asyncio
import logging
from keyboard_listener import KeyboardListener
import main_client
from logger import Logging, CallbackHandler

CONFIG_FILE = "config.json"

DEFAULT_WATCHER = {
    "channel_id": "",
    "file_path": "output.txt",
    "last_id_file": "last_id.txt",
    "interval": 10,
    "history_limit": 10,
    "show_author_mode": "both",
    "ignore_mode": None,
    "manual_clear": False,
    "txt_output": True,
    "max_rows_per_column": 9,
    "max_column_width": 40,
    "header_text": "",
    "column_spacing": 2
}


class ConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Watcher Config")
        self.root.geometry("1400x700")

        # Inicializuj logger s GUI callbackem
        self.logging_ctx = Logging()
        self.logger = logging.getLogger("DiscordWatcher")
        
        self.config = self.load_config()
        self.bot_running = False

        # TOKEN INPUT (na jednom řádku vedle sebe)
        token_frame = tk.Frame(root)
        token_frame.pack(anchor="w", padx=10, pady=5)
        
        tk.Label(token_frame, text="Discord BOT TOKEN:", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 10))
        self.token_entry = tk.Entry(token_frame, width=80)
        self.token_entry.pack(side="left", fill="x", expand=True)
        self.token_entry.insert(0, self.config.get("TOKEN", ""))

        # BUTTONS (pod tokenem)
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Add Watcher", command=self.add_watcher).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Save Configuration", command=self.save_config).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Run Bot", command=self.run_bot).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Delete Files (d)", command=self.delete_files).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Quit Bot (q)", command=self.quit_bot).pack(side="left", padx=5)

        # PANED WINDOW (dělič mezi watchers a logy)
        paned = tk.PanedWindow(root, orient="horizontal", sashwidth=5)
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # LEVÁ STRANA: WATCHERS
        left_frame = tk.Frame(paned)
        paned.add(left_frame, width=700)
        
        tk.Label(left_frame, text="Watchers:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        
        container = tk.Frame(left_frame)
        container.pack(fill="both", expand=True, padx=5, pady=5)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.scroll_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # PRAVÁ STRANA: LOGY
        right_frame = tk.Frame(paned)
        paned.add(right_frame, width=700)
        
        tk.Label(right_frame, text="Logs:", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
        log_frame = tk.Frame(right_frame)
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.log_text = tk.Text(log_frame, height=8, width=100, state=tk.DISABLED, bg="white", fg="black", font=("Arial", 9))
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")

        # Přidej CallbackHandler pro zápis do log panelu
        gui_handler = CallbackHandler(sink_text=self._log_to_text_widget, level=logging.DEBUG)
        gui_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
        self.logging_ctx.log_printer.add_handler(gui_handler)

        # zavěsit handler pro kliknutí na křížek okna
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Přidat key bindings pro 'd' a 'q' (když je GUI aktivní okno)
        self.root.bind('<d>', lambda e: self.on_key_press('d'))
        self.root.bind('<q>', lambda e: self.on_key_press('q'))

        #self.logger.info("GUI initialized.")
        self.render_watchers()

    # ----------------------------------------------------------------
    def on_key_press(self, key: str):
        """Handler pro stisk klávesy v GUI okně."""
        if key == 'd':
            self.delete_files()
        elif key == 'q':
            self.quit_bot()

    # ----------------------------------------------------------------
    def _log_to_text_widget(self, msg: str):
        """Callback pro CallbackHandler — přidej zprávu do log panelu."""
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    # ----------------------------------------------------------------
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return {"TOKEN": "", "watchers": []}

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)

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
        for idx, watcher in enumerate(self.config["watchers"]):
            self.render_one_watcher(idx, watcher)

    # ----------------------------------------------------------------
    def render_one_watcher(self, idx, watcher):
        """Render a watcher v multi-column layout pro úsporu vertikálního místa."""
        lf = ttk.LabelFrame(self.scroll_frame, text=f"Watcher {idx+1}")
        lf.pack(fill="x", padx=10, pady=5)

        # ROW = logická řada, která se bude přepočítávat na grid
        # Každý "row" ve smyslu gridu se může skládat z více sloupců
        row = 0

        # -- První řádek: Channel ID, Output File, Last ID File
        tk.Label(lf, text="Channel ID:").grid(row=row, column=0, sticky="w")
        channel_entry = tk.Entry(lf, width=20)
        channel_entry.insert(0, str(watcher.get("channel_id", "")))
        channel_entry.grid(row=row, column=1, sticky="w")
        watcher["channel_id_entry"] = channel_entry

        tk.Label(lf, text="Output File:").grid(row=row, column=2, sticky="w")
        file_entry = tk.Entry(lf, width=20)
        file_entry.insert(0, str(watcher.get("file_path", "")))
        file_entry.grid(row=row, column=3, sticky="w")
        watcher["file_path_entry"] = file_entry

        tk.Label(lf, text="Last ID File:").grid(row=row, column=4, sticky="w")
        last_id_entry = tk.Entry(lf, width=20)
        last_id_entry.insert(0, str(watcher.get("last_id_file", "")))
        last_id_entry.grid(row=row, column=5, sticky="w")
        watcher["last_id_file_entry"] = last_id_entry
        row += 1

        # -- Druhý řádek: Interval, History Limit, Rows per Column, Column Width
        tk.Label(lf, text="Interval:").grid(row=row, column=0, sticky="w")
        interval_entry = tk.Entry(lf, width=10)
        interval_entry.insert(0, str(watcher.get("interval", 10)))
        interval_entry.grid(row=row, column=1, sticky="w")
        watcher["interval_entry"] = interval_entry

        tk.Label(lf, text="History Limit:").grid(row=row, column=2, sticky="w")
        history_entry = tk.Entry(lf, width=10)
        history_entry.insert(0, str(watcher.get("history_limit", 10)))
        history_entry.grid(row=row, column=3, sticky="w")
        watcher["history_limit_entry"] = history_entry

        tk.Label(lf, text="Rows/Column:").grid(row=row, column=4, sticky="w")
        rows_entry = tk.Entry(lf, width=5)
        rows_entry.insert(0, str(watcher.get("max_rows_per_column", 9)))
        rows_entry.grid(row=row, column=5, sticky="w")
        watcher["max_rows_per_column_entry"] = rows_entry
        row += 1

        tk.Label(lf, text="Column Width:").grid(row=row, column=0, sticky="w")
        col_width_entry = tk.Entry(lf, width=5)
        col_width_entry.insert(0, str(watcher.get("max_column_width", 40)))
        col_width_entry.grid(row=row, column=1, sticky="w")
        watcher["max_column_width_entry"] = col_width_entry

        # -- Třetí řádek: Ignore Mode, Show Author
        tk.Label(lf, text="Ignore Mode:").grid(row=row, column=2, sticky="w")
        ignore_combo = ttk.Combobox(lf, values=["None", "bot", "human"], width=12)
        ignore_combo.set(str(watcher.get("ignore_mode", "None")))
        ignore_combo.grid(row=row, column=3, sticky="w")
        watcher["ignore_combo"] = ignore_combo

        tk.Label(lf, text="Show Author:").grid(row=row, column=4, sticky="w")
        author_combo = ttk.Combobox(lf, values=["both", "human", "bot", "None"], width=12)
        author_combo.set(str(watcher.get("show_author_mode", "both")))
        author_combo.grid(row=row, column=5, sticky="w")
        watcher["author_combo"] = author_combo
        row += 1

        # -- Čtvrtý řádek: checkboxes + header text
        manual_var = tk.BooleanVar(value=watcher.get("manual_clear", False))
        txt_var = tk.BooleanVar(value=watcher.get("txt_output", True))

        tk.Checkbutton(lf, text="Manual Clear (d)", variable=manual_var).grid(row=row, column=0, sticky="w")
        watcher["manual_var"] = manual_var

        tk.Checkbutton(lf, text="TXT Output", variable=txt_var).grid(row=row, column=1, sticky="w")
        watcher["txt_var"] = txt_var

        tk.Label(lf, text="Header:").grid(row=row, column=2, sticky="w")
        header_entry = tk.Entry(lf, width=16)
        header_entry.insert(0, str(watcher.get("header_text", "")))
        header_entry.grid(row=row, column=3, sticky="w")
        watcher["header_entry"] = header_entry

        # -- Poslední: Remove button
        tk.Button(lf, text="Remove", fg="red", command=lambda: self.remove_watcher(idx)).grid(row=row, column=5, sticky="e")


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
        self.config["TOKEN"] = self.token_entry.get()
        clean_watchers = []
        for w in self.config["watchers"]:
            clean = {
                "channel_id": w.get("channel_id_entry").get() if "channel_id_entry" in w else w.get("channel_id", ""),
                "file_path": w.get("file_path_entry").get() if "file_path_entry" in w else w.get("file_path", "output.txt"),
                "last_id_file": w.get("last_id_file_entry").get() if "last_id_file_entry" in w else w.get("last_id_file", "last_id.txt"),
                "interval": int(w.get("interval_entry").get() if "interval_entry" in w else w.get("interval", 10)),
                "history_limit": int(w.get("history_limit_entry").get() if "history_limit_entry" in w else w.get("history_limit", 10)),
                "show_author_mode": None if (w.get("author_combo") and w["author_combo"].get() == "None") else (w.get("author_combo").get() if "author_combo" in w else w.get("show_author_mode", "both")),
                "ignore_mode": None if (w.get("ignore_combo") and w["ignore_combo"].get() == "None") else (w.get("ignore_combo").get() if "ignore_combo" in w else w.get("ignore_mode", None)),
                "manual_clear": w.get("manual_var").get() if "manual_var" in w else bool(w.get("manual_clear", False)),
                "txt_output": w.get("txt_var").get() if "txt_var" in w else bool(w.get("txt_output", True)),
                "header_text": w.get("header_entry").get() if "header_entry" in w else str(w.get("header_text", "")),
                "max_rows_per_column": int(w.get("max_rows_per_column_entry").get() if "max_rows_per_column_entry" in w else w.get("max_rows_per_column", 9)),
                "max_column_width": int(w.get("max_column_width_entry").get() if "max_column_width_entry" in w else w.get("max_column_width", 40)),
                "column_spacing": int(w.get("column_spacing", 2))
            }
            clean_watchers.append(clean)
        config=self.config.copy()
        config["watchers"] = clean_watchers
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        self.logger.info("Configuration saved successfully.")

    # ----------------------------------------------------------------
    def run_bot(self):
        if self.bot_running:
            self.logger.warning("Bot already running.")
            return

        self.save_config()
        for w in self.config["watchers"]:
            # Zamknout vstupy
            for k in ["channel_id_entry","file_path_entry","last_id_file_entry","interval_entry","history_limit_entry","header_entry"]:
                if k in w: w[k].config(state="disabled")
            if "author_combo" in w: w["author_combo"].config(state="disabled")
            if "ignore_combo" in w: w["ignore_combo"].config(state="disabled")
        self.bot_running = True
        self.logger.info("Discord bot launched. Inputs locked.")

        # vytvořit nový loop a keyboard listener, spustit je v pozadí
        here = os.path.dirname(os.path.abspath(__file__))
        loop = asyncio.new_event_loop()
        kb = KeyboardListener(loop)
        kb.start()

        def target():
            try:
                main_client.run_client_with_loop(self.config, loop, keyboard_listener=kb)
            except Exception as e:
                self.logger.error(f"Client launch failed: {e}")

        t = threading.Thread(target=target, daemon=True)
        t.start()

        # ensure state
        self._bot_thread = t
        self._kb = kb
        self.bot_running = True

    # ----------------------------------------------------------------
    def stop_bot(self, wait_secs: float = 1.0):
        """Ukončí pouze běžícího bota (spuštěného přes Run Bot) a jeho keyboard listener.
        GUI zůstane otevřené.
        """
        # nic dělat, pokud není co zastavovat
        if not getattr(self, "_kb", None) and not getattr(self, "_bot_thread", None):
            self.bot_running = False
            return

        self.logger.info("Stoping bot...")
        # Pošleme 'q' do listeneru (pokud existuje) -> listener zavolá loop.stop()
        try:
            if getattr(self, "_kb", None):
                try:
                    self._kb.emit_key("q")
                except Exception:
                    pass
                # zastavit i samotný listener thread
                try:
                    self._kb.stop()
                except Exception:
                    pass
                try:
                    self._kb.join(timeout=wait_secs)
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ Listener stoping failed: {e}")

        # počkat krátce na ukončení bot-threadu
        try:
            if getattr(self, "_bot_thread", None):
                try:
                    self._bot_thread.join(timeout=wait_secs)
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ Wating on bot thread: {e}")

        # uklidit reference a stav
        self._kb = None
        self._bot_thread = None
        self.bot_running = False
        self.logger.info("Bot stoped.")

    # ----------------------------------------------------------------
    def send_key_to_bot(self, key: str):
        """Emuluj stisk klávesy -> pošli do KeyboardListener (pokud běží)."""
        if not getattr(self, "_kb", None) or not self.bot_running:
            self.logger.warning("Bot isn't running.")
            return
        try:
            self._kb.emit_key(key)
        except Exception as e:
            self.logger.error(f"Key sending failed: {e}")

    # ----------------------------------------------------------------
    def delete_files(self):
        # pokud běží bot, emuluj 'd' (watchery tak smažou svůj obsah)
        if self.bot_running and getattr(self, "_kb", None):
            self.send_key_to_bot("d")
            self.logger.info("Sent key 'd' to watchers.")
            return

        # fallback: mazání souborů lokálně
        if not self.bot_running:
            self.logger.warning("Start bot for delete files.")
            return
        for w in self.config["watchers"]:
            try:
                os.remove(w["file_path"])
            except FileNotFoundError:
                pass
        self.logger.info("Watcher files deleted.")

    # ----------------------------------------------------------------
    def quit_bot(self):
        # pokud běží bot a máme listener, pouze ho zastav a NEZAVÍREJ GUI
        if self.bot_running and getattr(self, "_kb", None):
            self.stop_bot()
            self.logger.info("Bot stoped")
            return

        if not self.bot_running:
            self.root.quit()
            return
        self.bot_running = False
        self.logger.info("Bot stopped.")
        self.root.quit()

    # ----------------------------------------------------------------
    def on_close(self):
        """Handler pro kliknutí na křížek okna.
        Po stisku X: pokud běží bot, zastav ho (stop_bot) a poté ukonči GUI a aplikaci.
        (Chování: Quit Bot tlačítko -> zastaví bota a GUI zůstane; X -> zastaví bota a ukončí vše.)
        """
        try:
            if self.bot_running:
                # Ujisti se, že vše, co jsme spustili, je správně ukončeno.
                try:
                    # Požádej o zastavení (emit 'q', stop listeneru, join thread)
                    self.stop_bot(wait_secs=2.0)
                except Exception as e:
                    # logni, ale pokračuj v ukončení GUI
                    try:
                        self.logger.error(f"Bot stopping failed during closing GUI: {e}")
                    except Exception:
                        pass
            # Po pokusu o zastavení bota ukonči GUI
            try:
                self.root.destroy()
            except Exception:
                try:
                    self.root.quit()
                except Exception:
                    pass
        except Exception:
            # fallback: pokud cokoli selže, zkusme GUI ukončit
            try:
                self.root.destroy()
            except Exception:
                try:
                    self.root.quit()
                except Exception:
                    pass


# --------------------------------------------------------------------
root = tk.Tk()
ConfigGUI(root)
root.mainloop()
