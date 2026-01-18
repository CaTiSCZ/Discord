#dispatecher.py
import logging
from logger import setup_logger

logger = setup_logger("Dispatcher", level=logging.DEBUG)

class MessageDispatcher:
    def __init__(self):
        # Mapa: channel_id (string) -> list instancí ChannelWatcher
        self._watchers = {}

    def register(self, channel_id, watcher_instance):
        """Zaregistruje watcher k odběru zpráv pro konkrétní ID kanálu."""
        cid = str(channel_id)
        if cid not in self._watchers:
            self._watchers[cid] = []
        self._watchers[cid].append(watcher_instance)
        logger.debug(f"Watcher zaregistrován pro ID: {cid}")

    async def dispatch_discord(self, message):
        """Doručí zprávu z Discordu správným watcherům."""
        cid = str(message.channel.id)
        if cid in self._watchers:
            for watcher in self._watchers[cid]:
                await watcher.on_new_message(message)

    async def dispatch_manual(self, target_id, text, author="Manual"):
        """
        Doručí manuální zprávu z GUI. 
        target_id může být buď ID kanálu nebo název panelu (panel-a atd.).
        """
        tid = str(target_id)
        if tid in self._watchers:
            for watcher in self._watchers[tid]:
                await watcher.on_manual_input(text, author)
    async def dispatch_discord_edit(self, message):
        cid = str(message.channel.id)
        if cid in self._watchers:
            for watcher in self._watchers[cid]:
                await watcher.on_message_edit(message)

    async def dispatch_clear(self, target_id=None):
        """
        Rozesílá příkaz ke smazání (klávesa 'd').
        Pokud target_id není zadáno, zkusí smazat expirované zprávy ve všech watcherech.
        """
        if target_id:
            tid = str(target_id)
            if tid in self._watchers:
                for watcher in self._watchers[tid]:
                    await watcher.clear_content()
        else:
            # Smaž ve všech registrovaných watcherech
            for watchers_list in self._watchers.values():
                for watcher in watchers_list:
                    await watcher.clear_content()

# Globální instance pro snadný import napříč projektem
dispatcher = MessageDispatcher()