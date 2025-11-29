#config_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
import subprocess

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
    "column_spacing": 2
}


class ConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Watcher Config")
        self.root.geometry("800x600")

        self.config = self.load_config()

        # TOKEN INPUT
        tk.Label(root, text="Discord BOT TOKEN:", font=("Arial", 12, "bold")).pack(anchor="w", pady=5)
        self.token_entry = tk.Entry(root, width=60)
        self.token_entry.pack(anchor="w", padx=10)
        self.token_entry.insert(0, self.config.get("TOKEN", ""))

        # SCROLLABLE AREA
        container = tk.Frame(root)
        container.pack(fill="both", expand=True, pady=10)

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

        # BUTTONS
        tk.Button(root, text="Add Watcher", command=self.add_watcher).pack(pady=5)
        tk.Button(root, text="Save Configuration", command=self.save_config).pack(pady=5)
        tk.Button(root, text="Run Bot", command=self.run_bot).pack(pady=5)

        self.render_watchers()

    # ----------------------------------------------------------------

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return {"TOKEN": "", "watchers": []}

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # FORCE normalize watchers to dictionary structure without widgets
            clean = []
            for w in cfg.get("watchers", []):
                new_w = DEFAULT_WATCHER.copy()
                new_w.update(w)  # keep existing values
                clean.append(new_w)

            cfg["watchers"] = clean
            return cfg

        except json.JSONDecodeError:
            messagebox.showerror("Error", "config.json is corrupted. Creating a new one.")
            return {"TOKEN": "", "watchers": []}

    # ----------------------------------------------------------------

    def render_watchers(self):
        """Clear and re-draw all watchers."""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        for idx, watcher in enumerate(self.config["watchers"]):
            self.render_one_watcher(idx, watcher)

    # ----------------------------------------------------------------

    def render_one_watcher(self, idx, watcher):
        """Render a watcher and inject widget references into watcher dict."""
        lf = ttk.LabelFrame(self.scroll_frame, text=f"Watcher {idx+1}")
        lf.pack(fill="x", padx=10, pady=5)

        row = 0

        def add_row(label, key, width=25):
            nonlocal row
            tk.Label(lf, text=label).grid(row=row, column=0, sticky="w")

            entry = tk.Entry(lf, width=width)
            entry.insert(0, str(watcher.get(key, "")))
            entry.grid(row=row, column=1, sticky="w")

            watcher[key + "_entry"] = entry
            row += 1

        # Base fields
        add_row("Channel ID:", "channel_id")
        add_row("Output File:", "file_path")
        add_row("Last ID File:", "last_id_file")
        add_row("Interval:", "interval")
        add_row("History Limit:", "history_limit")
        add_row("Rows Per Column:", "max_rows_per_column")
        add_row("Column Width:", "max_column_width")

        # Combobox: ignore mode
        tk.Label(lf, text="Ignore Mode:").grid(row=row, column=0, sticky="w")
        ignore_combo = ttk.Combobox(lf, values=["None", "bot", "human"], width=22)
        ignore_combo.set(str(watcher.get("ignore_mode", "None")))
        ignore_combo.grid(row=row, column=1, sticky="w")
        watcher["ignore_combo"] = ignore_combo
        row += 1

        # Combobox: show author
        tk.Label(lf, text="Show Author:").grid(row=row, column=0, sticky="w")
        author_combo = ttk.Combobox(lf, values=["both", "human", "bot", "None"], width=22)
        author_combo.set(str(watcher.get("show_author_mode", "both")))
        author_combo.grid(row=row, column=1, sticky="w")
        watcher["author_combo"] = author_combo
        row += 1

        # Checkboxes
        manual_var = tk.BooleanVar(value=watcher.get("manual_clear", False))
        txt_var = tk.BooleanVar(value=watcher.get("txt_output", True))

        tk.Checkbutton(lf, text="Manual Clear (d)", variable=manual_var).grid(row=row, column=0, sticky="w")
        watcher["manual_var"] = manual_var
        row += 1

        tk.Checkbutton(lf, text="TXT Output", variable=txt_var).grid(row=row, column=0, sticky="w")
        watcher["txt_var"] = txt_var
        row += 1

        # Remove button
        tk.Button(lf, text="Remove", fg="red",
                  command=lambda: self.remove_watcher(idx)).grid(row=row, column=1, sticky="e")

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
        """Extract values from widget entries into a clean JSON dict."""
        self.config["TOKEN"] = self.token_entry.get()

        clean_watchers = []

        for w in self.config["watchers"]:
            # bezpečné získání hodnot z Entry/Combo/Var, fallback na existující hodnotu ve slovníku
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
                "max_rows_per_column": int(w.get("max_rows_per_column_entry").get() if "max_rows_per_column_entry" in w else w.get("max_rows_per_column", 9)),
                "max_column_width": int(w.get("max_column_width_entry").get() if "max_column_width_entry" in w else w.get("max_column_width", 40)),
                "column_spacing": int(w.get("column_spacing", 2))
            }

            clean_watchers.append(clean)

        self.config["watchers"] = clean_watchers

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

        messagebox.showinfo("Saved", "Configuration saved successfully.")


    # ----------------------------------------------------------------

    def run_bot(self):
        # Uložíme konfiguraci – opravené save_config už zvládá nové i staré watchery
        self.save_config()

        # Absolutní cesta k main_client.py
        here = os.path.dirname(os.path.abspath(__file__))
        main_path = os.path.join(here, "main_client.py")

        # Debug výpisy
        print("DEBUG: __file__ =", __file__)
        print("DEBUG: here =", here)
        print("DEBUG: main_path =", main_path)
        print("DEBUG: exists(main_path) =", os.path.exists(main_path))

        if not os.path.exists(main_path):
            messagebox.showerror("Error", f"main_client.py not found at:\n{main_path}")
            return

        # Zajistit python.exe (ne pythonw.exe)
        python_exec = os.path.join(os.path.dirname(sys.executable), "python.exe")
        print("DEBUG: using python_exec:", python_exec)

        # Spustit bota jako samostatný proces
        subprocess.Popen([python_exec, main_path], cwd=here)

        messagebox.showinfo("Bot Running", "Discord bot launched.")

        # Ukončí GUI, ale bez znovu-renderu
        self.root.quit()


# --------------------------------------------------------------------
root = tk.Tk()
ConfigGUI(root)
root.mainloop()
