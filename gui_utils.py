import tkinter as tk
from tkinter import ttk, messagebox


def show_messagebox(parent, title, message, kind="info", width=320):
    """Zobrazí message box nad rodičovským oknem a vycentruje ji do jeho plochy."""
    if parent is None:
        if kind == "error":
            return messagebox.showerror(title, message)
        if kind == "warning":
            return messagebox.showwarning(title, message)
        return messagebox.showinfo(title, message)

    parent_window = parent if hasattr(parent, "winfo_exists") else None
    if parent_window is None:
        return show_messagebox(None, title, message, kind=kind, width=width)

    dialog = tk.Toplevel(parent_window)
    dialog.withdraw()
    dialog.transient(parent_window)
    dialog.title(title)

    icon = {"info": "ℹ", "warning": "⚠", "error": "✖"}.get(kind, "ℹ")
    ttk.Label(dialog, text=f"{icon} {message}", wraplength=width - 40, justify="center").pack(padx=20, pady=(16, 8))
    ttk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=(0, 16))

    dialog.update_idletasks()
    req_w = dialog.winfo_reqwidth()
    req_h = dialog.winfo_reqheight()

    if hasattr(parent_window, "winfo_rootx") and hasattr(parent_window, "winfo_rooty"):
        x = parent_window.winfo_rootx() + max(0, (parent_window.winfo_width() - req_w) // 2)
        y = parent_window.winfo_rooty() + max(0, (parent_window.winfo_height() - req_h) // 2)
        dialog.geometry(f"+{x}+{y}")

    dialog.deiconify()
    dialog.grab_set()
    dialog.focus_set()
    dialog.wait_window()


class FocusManager:
    """
    MixIn třída pro Tkinter okna.
    Zajišťuje, že popup okna správně převezmou focus při otevření
    a že kliknutí na prázdnou plochu nebo jiné neinteraktivní prvky
    odebere focus aktivnímu vstupnímu poli.
    """
    def setup_focus_management(self):
        self.bind("<ButtonPress-1>", self._handle_global_click, add="+")
        self.bind("<ButtonPress-2>", self._handle_global_click, add="+")
        self.bind("<ButtonPress-3>", self._handle_global_click, add="+")
        self.bind("<Map>", self._handle_window_show, add="+")

    def _handle_window_show(self, event=None):
        if getattr(event, "widget", None) is self:
            self.after(0, self._restore_window_focus)

    def _restore_window_focus(self):
        if not self.winfo_exists():
            return
        try:
            self.focus_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _handle_global_click(self, event):
        if not hasattr(event, "widget"):
            return

        clicked_widget = event.widget
        try:
            clicked_toplevel = clicked_widget.winfo_toplevel()
        except Exception:
            return

        if clicked_toplevel is not self:
            return

        focus_widgets = (ttk.Entry, ttk.Combobox, tk.Entry, tk.Text, tk.Scale, ttk.Button, tk.Button)
        if isinstance(clicked_widget, focus_widgets):
            return

        self._restore_window_focus()

class WindowPositionMixIn:
    """MixIn pro chytré umisťování oken vůči rodiči."""
    
    def place_relative_to(self, reference_window, position="center", offset_x=0, offset_y=0):
        """
        Umístí okno relativně k referenčnímu oknu.
        Vnitřní pozice: 'center', 'nw', 'ne', 'sw', 'se'
        Vnější pozice: 'out_right', 'out_left', 'out_top', 'out_bottom'
        """
        reference_window.update_idletasks()
        self.update_idletasks()

        # Rozměry a pozice rodiče v absolutních souřadnicích obrazovky
        ref_x = reference_window.winfo_rootx()
        ref_y = reference_window.winfo_rooty()
        ref_w = reference_window.winfo_width()
        ref_h = reference_window.winfo_height()

        # Rozměry aktuálního okna (self)
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()

        # VÝPOČET ZÁKLADNÍ POZICE
        if position == "center":
            x = ref_x + (ref_w // 2) - (width // 2)
            y = ref_y + (ref_h // 2) - (height // 2)
        elif position == "nw": # North-West (vnitřní)
            x, y = ref_x, ref_y
        elif position == "ne": # North-East (vnitřní)
            x, y = ref_x + ref_w - width, ref_y
        elif position == "sw": # South-West (vnitřní)
            x, y = ref_x, ref_y + ref_h - height
        elif position == "se": # South-East (vnitřní)
            x, y = ref_x + ref_w - width, ref_y + ref_h - height
            
        # VNĚJŠÍ POZICE
        elif position == "out_right": # Vpravo vedle rodiče
            x, y = ref_x + ref_w, ref_y
        elif position == "out_left": # Vlevo vedle rodiče
            x, y = ref_x - width, ref_y
        elif position == "out_top": # Nad rodičem
            x, y = ref_x, ref_y - height
        elif position == "out_bottom": # Pod rodičem
            x, y = ref_x, ref_y + ref_h
        else:
            x = ref_x + (ref_w // 2) - (width // 2)
            y = ref_y + (ref_h // 2) - (height // 2)

        # APLIKACE OFFSETŮ
        final_x = x + offset_x
        final_y = y + offset_y

        self.geometry(f"+{final_x}+{final_y}")
        self.deiconify()  # Zobrazí okno až na správných souřadnicích
        self.focus_force()