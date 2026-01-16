#main_client.py
import discord
import asyncio
import json
import os

import logging

from channel_watcher import ChannelWatcher
from keyboard_listener import KeyboardListener
from web.server import sio, start_web_server, stop_web_server
from logger import setup_logger

logger = setup_logger("Engine", level=logging.DEBUG)
CONFIG_FILE = "config.json"

class DiscordEngine:
    def __init__(self, config=None):
        # Pokud config nepředáme (např. při startu bez GUI), načteme ho ze souboru
        self.config = config or self.load_config()
        self.loop = None
        self.client = None
        self.kb_listener = None
        self.is_running = False

    def load_config(self):
        """Načtení konfigurace uložené z GUI."""
        if not os.path.exists(CONFIG_FILE):
            logger.error(f"{CONFIG_FILE} not found.")
            return {"watchers": []}
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _start_watchers(self):
        """Inicializace watcherů a registrace jejich callbacků pro klávesnici."""
        if not self.config.get("watchers"):
            logger.warning("No watchers in config.")
            return

        for w in self.config["watchers"]:
            comment = w.get("comment", "No description")
            channel_id = w.get("channel_id")
            if not w.get("enabled", True):
                logger.debug(f"Skipping watcher: [{comment}] (ID: {channel_id})")
                continue
            
            logger.info(f"Start watcher: [{comment}] (ID: {channel_id})")
            
            # Vytvoření instance watcheru
            watcher = ChannelWatcher(
                client=self.client,
                channel_id=int(w.get("channel_id", 0)),
                file_path=str(w.get("file_path", "output.txt")),
                last_id_file=str(w.get("last_id_file", "last_id.txt")),
                socket_panel=str(w.get("socket_panel", "panel-a")),
                interval=int(w.get("interval", 10)),
                history_limit=int(w.get("history_limit", 10)),
                show_author_mode=str(w.get("show_author_mode", "both")),
                ignore_mode=w.get("ignore_mode"),
                manual_clear=bool(w["manual_clear"]),
                max_rows_per_column=int(w.get("max_rows_per_column", 9)),
                max_column_width=int(w.get("max_column_width", 40)),
                column_spacing=int(w.get("column_spacing", 2)),
                txt_output=bool(w.get("txt_output", True)),
                header_text=str(w.get("header_text", "")),
                loop=self.loop,
                sio=sio,
            )
            logger.debug(f"Watcher created: [{comment}] (ID: {watcher.channel_id}) \n\tpanel: {watcher.socket_panel}, file: {watcher.file_path}\n\tClient: {self.client} ({watcher.client})")
            # REGISTRACE CALLBACKU (Důležité!)
            # Když se na klávesnici zmáčkne klávesa, watcher dostane šanci reagovat
            if self.kb_listener:
                self.kb_listener.register_callback(watcher.on_keypress)

            # Spuštění watcheru jako asynchronní task
            self.loop.create_task(watcher.run())

    async def run_async(self):
        """Hlavní asynchronní workflow."""
        TOKEN = self.config.get("TOKEN", "").strip()
        if not TOKEN:
            logger.error("TOKEN not defined in config.json.")
            raise RuntimeError("TOKEN not defined in config.json (use config_gui.py to set it).")
        
        self.is_running = True
        try:
            self.client = discord.Client(intents=discord.Intents.all())
            logger.debug("Discord Client initialized.")
        except Exception as e:
            logger.error(f"Discord Client init error: {e}")
            raise e
        
        @self.client.event
        async def on_ready():
            logger.debug(f"Bot is logged in as {self.client.user}")
            # Teprve teď, když je bot READY, spustíme watchery
            await self._start_watchers()
            logger.debug("Watchers started after bot login.")
        
        try:
            self.loop.create_task(start_web_server())
            await self.client.start(TOKEN)
            
        except Exception as e:
            logger.error(f"Error of Engine: {e}")
        finally:
            await self.shutdown_async()

    async def shutdown_async(self):
        """Čisté ukončení asynchronních součástí."""
        logger.info("Engine: Shutting down...")
        
        if self.client and not self.client.is_closed():
            await self.client.close()
        
        await stop_web_server()
        
        # Zrušení všech visících tasků
        tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task()]
        for t in tasks: t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.is_running = False
        logger.info("Engine: All process stopped.")
        self.loop.stop()

    def start(self, loop):
        """Vstupní bod pro thread (z GUI nebo Mainu)."""
        self.loop = loop
        asyncio.set_event_loop(self.loop)
        
        # Inicializace klávesnice
        self.kb_listener = KeyboardListener(self.loop)
        self.kb_listener.start()
        
        # Spuštění asynchronního světa
        try:
            self.loop.run_until_complete(self.run_async())
        except Exception as e:
            logger.error(f"Loop error: {e}")

    def stop(self):
        """Signál k ukončení vyslaný z jiného vlákna (GUI)."""
        if self.kb_listener:
            self.kb_listener.stop()
        
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.shutdown_async(), self.loop)

