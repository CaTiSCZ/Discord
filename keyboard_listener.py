# keyboard_listener.py
import threading
import asyncio
import sys

class KeyboardListener(threading.Thread):
    def __init__(self, loop: asyncio.AbstractEventLoop, watchers=None):
        super().__init__()
        self.loop = loop
        self.watchers = watchers or []
        self.daemon = True  # vláknu nemusí čekat na ukončení
        self._stop_event = threading.Event()
        self.delete_key = None

    def stop(self):
        self._stop_event.set()
        try:
            import ctypes
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(self.ident), ctypes.py_object(KeyboardInterrupt))
        except Exception:
            pass

    def run(self):
        print("💡 KeyboardListener spuštěn. Pro ukončení napište 'q' + Enter.")
        while True:
            try:
                user_input = input()
                if user_input.strip().lower() == "q":
                    print("⚡ KeyboardListener: Ukončuji script...")
                    # bezpečně zastaví asyncio loop
                    for w in self.watchers:
                        w.running = False
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    break
                elif user_input.strip().lower() == "d":
                    self.delete_key = "d"
            except (EOFError, KeyboardInterrupt):
                # ochrana proti neočekávanému přerušení
                self.loop.call_soon_threadsafe(self.loop.stop)
                break
