# keyboard_listener.py
import threading
import asyncio
import sys

class KeyboardListener(threading.Thread):
    """
    Třída poslouchá klávesnici ve vlastním vlákně.
    Při stisknutí 'q' a Enter ukončí hlavní asyncio loop.
    """
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.daemon = True  # vláknu nemusí čekat na ukončení

    def run(self):
        print("💡 KeyboardListener spuštěn. Pro ukončení napište 'q' + Enter.")
        while True:
            try:
                user_input = input()
                if user_input.strip().lower() == "q":
                    print("⚡ Ukončuji script...")
                    # bezpečně zastaví asyncio loop
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    break
            except (EOFError, KeyboardInterrupt):
                # ochrana proti neočekávanému přerušení
                self.loop.call_soon_threadsafe(self.loop.stop)
                break
