#dispatecher.py
import logging
from logger import setup_logger
import asyncio

logger = setup_logger("Dispatcher", level=logging.DEBUG)

class MessageDispatcher:
    def __init__(self):
        # Mapa: channel_id (string) -> list instancí ChannelWatcher
        self._watchers = {}
        self.connection_callback = None
        self.loop = None

    def set_connection_callback(self, callback):
        """GUI si sem zaregistruje svou funkci pro změnu barvy kolečka."""
        self.connection_callback = callback

    async def update_connection_status(self, is_connected):
        """Tuto metodu volá server."""
        if self.connection_callback:
            self.connection_callback(is_connected)
        
    def register(self, channel_id, watcher_instance):
        """Zaregistruje watcher k odběru zpráv pro konkrétní ID kanálu."""
        cid = str(channel_id)
        if cid not in self._watchers:
            self._watchers[cid] = []
        self._watchers[cid].append(watcher_instance)
        logger.debug(f"Watcher registred for ID: {cid}")

    async def dispatch_discord(self, message):
        """Doručí zprávu z Discordu správným watcherům."""
        logger.debug(f"Dispatching Discord message from channel ID: {message.channel.id}")
        cid = str(message.channel.id)
        if cid in self._watchers:
            for watcher in self._watchers[cid]:
                try:
                    await watcher.on_new_message(message)
                    logger.debug(f"Message dispatched to watcher for channel ID: {cid}")
                except asyncio.CancelledError:
                    pass 
                except Exception as e:
                    logger.error(f"Error new message: {e}")
        else:
            logger.debug(f"No watchers registered for channel ID: {cid}")

    async def dispatch_manual(self, target_id, text, author="Manual", attachments=None):
        """
        Doručí manuální zprávu z GUI. 
        target_id může být buď ID kanálu nebo název panelu (panel-a atd.).
        """
        logger.debug(f"Dispatching manual message to {target_id} from {author}: {text}")
        tid = str(target_id)
        if tid in self._watchers:
            for watcher in self._watchers[tid]:
                try:
                    await watcher.on_manual_input(text, author, attachments)
                    logger.debug(f"Manual message dispatched to watcher for channel ID: {tid}")
                except asyncio.CancelledError:
                    pass 
                except Exception as e:
                    logger.error(f"Error new manual message: {e}")
        else:
            logger.debug(f"No watchers registered for target ID: {tid}")
                
    async def dispatch_discord_edit(self, message):
        cid = str(message.channel.id)
        if cid in self._watchers:
            for watcher in self._watchers[cid]:
                try:
                    await watcher.on_message_edit(message)
                    logger.debug(f"Eddit message dispatched to watcher for channel ID: {cid}")
                except asyncio.CancelledError:
                    pass 
                except Exception as e:
                    logger.error(f"Error edit message: {e}")

    async def on_key_press(self, key):
        match key.lower():
            case 'd':
                await self.dispatch_clear()

    async def dispatch_clear(self):
        for watchers_list in self._watchers.values():
            for watcher in watchers_list:
                try:
                    await watcher.clear_content()
                    logger.debug(f"Contend cleared")
                except asyncio.CancelledError:
                    pass 
                except Exception as e:
                    logger.error(f"Error clear contend: {e}")
                    

dispatcher = MessageDispatcher()