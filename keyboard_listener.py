# keyboard_listener.py
import threading
import asyncio
import msvcrt
import time

class KeyboardListener(threading.Thread):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.daemon = True
        self._stop_event = threading.Event()
        self.callbacks = []

    def register_callback(self, fn):
        """Třídy zaregistrují callback volaný při stisku klávesy."""
        if callable(fn):
            self.callbacks.append(fn)

    def stop(self):
        self._stop_event.set()

    def run(self):
        print("💡 KeyboardListener spuštěn (q = quit, d = delete).")
        while not self._stop_event.is_set():
            if msvcrt.kbhit():
                key = msvcrt.getwch().lower()

                # zavolat callbacky
                for fn in self.callbacks:
                    try:
                        fn(key)
                    except Exception as e:
                        print(f"❌ Chyba v callbacku: {e}")

                # globální exit
                if key == "q":
                    print("⚡ KeyboardListener: Ukončuji program…")
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    break

            time.sleep(0.05)
