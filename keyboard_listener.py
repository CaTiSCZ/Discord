# keyboard_listener.py
import threading
import asyncio
import msvcrt
import time
import queue
import logging
from logger import setup_logger

logger = setup_logger("KeyboardListener", level=logging.DEBUG)

class KeyboardListener(threading.Thread):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop = loop
        self.daemon = True
        self._stop_event = threading.Event()
        self.callbacks = []
        self._queue = queue.Queue()

    def register_callback(self, fn):
        """Třídy zaregistrují callback volaný při stisku klávesy."""
        if callable(fn):
            self.callbacks.append(fn)

    def emit_key(self, key: str):
        """Thread-safe vložení klávesy z jiného threadu (např. GUI)."""
        try:
            self._queue.put_nowait(str(key).lower())
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()

    def _handle_key(self, key: str):
        """Centralizované zpracování klávesy (volání callbacků + q behaviour)."""
        key = key.lower()
        for fn in self.callbacks:
            try:
                fn(key)
            except Exception as e:
                logger.error(f"Callback: {e}")

        if key == "q":
            logger.info("KeyboardListener: stopping event loop on 'q' keypress.")
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception:
                pass

    def run(self):
        logger.debug("KeyboardListener running (q = quit, d = delete).")
        while not self._stop_event.is_set():
            # nejdřív zpracovat programové klávesy z fronty
            try:
                while True:
                    k = self._queue.get_nowait()
                    self._handle_key(k)
            except queue.Empty:
                pass

            # pak zpracovat fyzické stisky
            if msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                self._handle_key(key)

            time.sleep(0.05)
