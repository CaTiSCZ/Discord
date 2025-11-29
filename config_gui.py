import tkinter as tk
from tkinter import ttk, messagebox
import json
import subprocess
import os

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
        self.root.title("Discord Watcher Configuration")
        self.root.geometry("750x650")

        self.config = self.load_config()

        # Token
        tk.Label(root, text="Discord BOT TOKEN:", font=("Arial", 12, "bold")).pack(anchor="w", pady=5)
        self.token_entry = tk.Entry(root, width=80)
        self.token_entry.pack()
        self.token_entry.insert(0, self.config.get("TOKEN", ""))

        # Watchers Label
        tk.Label(root, text="Watchers:", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)

        # Watchers Frame
        self.watcher_frame = tk.Frame(root, borderwidth=2, relief="groove")
        self.watcher_frame.pack(fill="both", expand=True)

        # Buttons
        tk.Button(root, text="Add Watcher", command=self.add_watcher).pack(pady=5)
        tk.Button(root, text="Save Configuration", command=self.save_config).pack(pady=5)
        tk.Button(root, text="Run Bot", command=self.run_bot).pack(pady=5)

        self.render_watchers()

    # ---------------------------------------------------
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return {"TOKEN": "", "watchers": []}

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------------------------------------------------
    def save_config(self):
        self.config["TOKEN"] = self.token_entry.get()

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

        messagebox.showinfo("Saved", "Configuration saved.")

    # ---------------------------------------------------
    def render_watchers(self):
        for child in self.watcher_frame.winfo_children():
            child.destroy()

        for i, watcher in enumerate(self.config["watchers"]):
            self.render_one_watcher(i, watcher)

    # ---------------------------------------------------
    def render_one_watcher(self, idx, watcher):
        frame = tk.LabelFrame(self.watcher_frame, text=f"Watcher #{idx + 1}", padx=10, pady=10)
        frame.pack(fill="x", padx=5, pady=5)

        def add_field(label, key, width=25):
            tk.Label(frame, text=label).pack(anchor="w")
            entry = tk.Entry(frame, width=width)
            entry.insert(0, watcher.get(key, ""))
            entry.pack(anchor="w")
            return entry

        # Basic fields
        watcher["channel_id_entry"] = add_field("Channel ID:", "channel_id")
        watcher["file_path_entry"] = add_field("Output File:", "file_path")
        watcher["last_id_file_entry"] = add_field("Last ID File:", "last_id_file")

        # Params
        watcher["interval_entry"] = add_field("Interval (sec):", "interval")
        watcher["history_limit_entry"] = add_field("History limit:", "history_limit")
        watcher["max_rows_entry"] = add_field("Max rows per column:", "max_rows_per_column")
        watcher["max_width_entry"] = add_field("Column width:", "max_column_width")

        # ignore mode
        tk.Label(frame, text="Ignore mode:").pack(anchor="w")
        ignore_combo = ttk.Combobox(frame, values=["None", "bot", "human"])
        ignore_combo.set(str(watcher.get("ignore_mode")))
        ignore_combo.pack(anchor="w")
        watcher["ignore_combo"] = ignore_combo

        # show author
        tk.Label(frame, text="Show author mode:").pack(anchor="w")
        author_combo = ttk.Combobox(frame, values=["both", "human", "bot", "None"])
        author_combo.set(str(watcher.get("show_author_mode")))
        author_combo.pack(anchor="w")
        watcher["author_combo"] = author_combo

        # checkboxes
        watcher["manual_var"] = tk.BooleanVar(value=watcher.get("manual_clear", False))
        tk.Checkbutton(frame, text="Manual clear (d)", variable=watcher["manual_var"]).pack(anchor="w")

        watcher["txt_var"] = tk.BooleanVar(value=watcher.get("txt_output", True))
        tk.Checkbutton(frame, text="TXT output instead of HTML", variable=watcher["txt_var"]).pack(anchor="w")

        # Remove
        tk.Button(frame, text="Remove watcher", fg="red",
                  command=lambda: self.remove_watcher(idx)).pack(anchor="e")

    # ---------------------------------------------------
    def add_watcher(self):
        self.config["watchers"].append(DEFAULT_WATCHER.copy())
        self.render_watchers()

    # ---------------------------------------------------
    def remove_watcher(self, idx):
        del self.config["watchers"][idx]
        self.render_watchers()

    # ---------------------------------------------------
    def run_bot(self):
        """Save config and then launch main_client.py."""
        self.save_config()

        if not os.path.exists("main_client.py"):
            messagebox.showerror("Error", "main_client.py not found!")
            return

        subprocess.Popen(["python", "main_client.py"])
        messagebox.showinfo("Bot Running", "Bot launched successfully.")
        self.root.quit()


# ---------------------------------------------------
# MAIN
root = tk.Tk()
gui = ConfigGUI(root)
root.mainloop()
