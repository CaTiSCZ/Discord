# channel_watcher_obr.py
import discord
import asyncio
import os
import re
import logging
from typing import List, Dict, Optional
import sys
import event

logger = logging.getLogger("DiscordWatcher.ChannelWatcherObr")

class ChannelWatcherObr:
    """
    Watcher pro automatické stahování obrázků z Discord kanálu
    a postupné generování jednoho HTML souboru každých X vteřin.
    """
    def __init__(
        self,
        client: discord.Client,
        channel_id: int,
        file_path: str,
        last_id_file: str,
        interval: int = 10,
        history_limit: int = 10,



    ):
        self.client = client
        self.channel_id = channel_id
        self.file_path = file_path
        self.last_id_file = last_id_file
        self.interval = interval
        self.history_limit = history_limit
        
        self.base_dir = Path(os.path.dirname(file_path))
        self.obr_dir = self.base_dir / "obr"
        self.obr_dir.mkdir(parents=True, exist_ok=True)
    

     # stav
        self.old_last_id: Optional[int] = None
        self.last_id: Optional[int] = None
        
        self.queue: List[Path] = []
        self.cache: List[Dict] = []
        self.running = True


    def load_last_ids(self):
        """Načte old_last_id a last_id z last_id_file (čitelné)."""
        if not os.path.exists(self.last_id_file):
            logger.info(f"last_id_file ({self.last_id_file}) not found.")
            self.old_last_id = None
            self.last_id = None
            return
        try:
            with open(self.last_id_file, "r", encoding="utf-8") as f:
                data = f.read().splitlines()
            kv = {}
            for line in data:
                if "=" in line:
                    k, v = line.split("=", 1)
                    kv[k.strip()] = int(v.strip())
            self.old_last_id = kv.get("old_last_id")
            self.last_id = kv.get("last_id")
            #print(f"[INIT] Načteny ID: old_last_id={self.old_last_id}, last_id={self.last_id}")
        except Exception as e:
            logger.error(f"ID file reading failed: {e}")
            self.old_last_id = None
            self.last_id = None

    def save_last_ids(self):
        """Uloží current old_last_id a last_id do souboru (čitelně)."""
        try:
            with open(self.last_id_file, "w", encoding="utf-8") as f:
                f.write(f"old_last_id={self.old_last_id or 0}\n")
                f.write(f"last_id={self.last_id or 0}\n")
            #print(f"[SAVE] last_id_file uložen: old_last_id={self.old_last_id}, last_id={self.last_id}")
        except Exception as e:
            logger.error(f"ID file saving failed: {e}")
        