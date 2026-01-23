#main_client.py
import discord
import asyncio
import json
import os

import logging

from channel_watcher import ChannelWatcher
from web.server import sio, start_web_server, stop_web_server
from logger import setup_logger
from dispatcher import dispatcher

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
        self.watchers = []
        comments = []
        for w in self.config["watchers"]:
            comment = w.get("comment", "No description")
            channel_id = w.get("channel_id")
            if not w.get("enabled", True):
                logger.debug(f"Skipping watcher: [{comment}] (ID: {channel_id})")
                continue
            # Vytvoření instance watcheru
            watcher = ChannelWatcher(self.client, w, sio)
            self.watchers.append(watcher)
            comments.append(comment)

        start_tasks = [
            watcher.start() 
            for watcher in self.watchers 
        ]

        if start_tasks:
            await asyncio.gather(*start_tasks)
            

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
        @self.client.event
        async def on_message(message):
            if message.author == self.client.user:
                return   
            await dispatcher.dispatch_discord(message)
        @self.client.event
        async def on_message_edit(before, after):
            await dispatcher.dispatch_discord_edit(after)
        
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
            try:
                await self.client.close()
                logger.debug("Engine: Discord client closed.")
            except Exception as e:
                logger.error(f"Engine: Error closing client: {e}")
        
        try:
            await stop_web_server()
        except Exception as e:
            logger.error(f"Engine: Error during server shutdown: {e}")
        
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

