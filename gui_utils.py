import tkinter as tk
from tkinter import ttk

class FocusManager:
    """
    MixIn třída pro Tkinter okna. 
    Zajišťuje, že kliknutí na 'mrtvé' místo (pozadí, labely) 
    odebere focus aktivnímu vstupnímu poli, čímž vyvolá FocusOut.
    """
    def setup_focus_management(self):
        # Bindujeme na úroveň této konkrétní instance okna
        self.bind("<Button-1>", self._handle_global_click)

    def _handle_global_click(self, event):
        # Seznam widgetů, které mají mít focus 
        # (při kliknutí na ně nechceme focus brát)
        focus_widgets = (ttk.Entry, ttk.Combobox, tk.Entry, tk.Text, tk.Scale)
        if not hasattr(event, "widget"): return
        clicked_widget = event.widget
        
        # Pokud klikneme na něco, co není v seznamu (např. Frame, Label, Canvas)
        if not isinstance(clicked_widget, focus_widgets):
            # Nastavíme focus na okno samotné, čímž vyvoláme FocusOut na aktivním poli
            self.focus_set()

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

        # Rozměry a pozice rodiče
        ref_x = reference_window.winfo_x()
        ref_y = reference_window.winfo_y()
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