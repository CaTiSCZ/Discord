# channel_watcher.py
import asyncio
import re
import logging
from typing import List
from types import SimpleNamespace
import time
from collections import deque
from logger import setup_logger
from dispatcher import dispatcher
import aiohttp

logger = setup_logger("ChannelWatcher", level=logging.DEBUG)

class MessageFormatter:
    def __init__(
        self, config):
        self.max_rows_per_column = config.get("max_rows_per_column", 9)
        self.max_column_width = config.get("max_column_width", 40)
        self.column_spacing = config.get("column_spacing", 2)
        self.show_author_mode = config.get("show_author_mode", "both")
        self.header_text = config.get("header_text", "")

    def format_messages(self, msgs):
        messages = []
        for msg in msgs:
            
            if msg.author.name == "Avrae":
                content = self._process_roll(msg) # obsahuje kompletní zprávu včetně jména hráče který hodil - může se rovnou předat pro zpracování do sloupců
            else:
                content = [self._normalize_line(l) for l in msg.content.splitlines()] # řádky zprávy zbavené markdown atd.
            is_bot =  msg.author.bot
            autor = re.sub(r"\s*\([^)]*\)\s*$", "", msg.author.display_name)
            messages.append({
                "content": content, # Již znormalizovaný text (bold, italika...)
                "author": autor,
                "is_bot": is_bot,
                "show_author": self.show_author_mode 
            }) 
        return messages
    
    def _process_roll(self, msg):
        """Rozhodne, jestli jde o single/multi roll a zavolá parser."""
        lines = [self._normalize_line(l) for l in msg.content.splitlines()]
        player_name = re.sub(r"\s*\([^)]*\)\s*$", "", msg.mentions[0].display_name)
        
        if len(lines) == 3:
            return self._parse_single_roll(lines, player_name)
        elif len(lines) >= 5:
            return self._parse_multi_roll(lines, player_name)
        return []    

    def _parse_single_roll(self, lines: List[str], player_name: str) -> List[str]:
        """Parse single roll (3 lines): player, rollline, total"""
        try:
            player_line, roll_line, total_value = lines
            
        except ValueError:
            return []
        return [f"{player_name}: {roll_line.strip()} = {total_value.strip()}"]

    def _parse_multi_roll(self, lines: List[str], player_name: str) -> List[str]:
        """
        Parse multi roll (≥5 lines). Vrací hlavičku a jednotlivé řádky s číslováním.
        Implementace věrná původní logice.
        """
        if not lines:
            return []
        rolling_line_idx = next((i for i, l in enumerate(lines) if "Rolling" in l), 1)
        rolling_line = lines[rolling_line_idx]
        user_text = (rolling_line.split(":", 1)[0].strip() + ": ") if ":" in rolling_line else ""

        iter_match = re.search(r"(\d+)\s*iterations", rolling_line, re.IGNORECASE)
        num_iterations = int(iter_match.group(1)) if iter_match else 1

        first_roll_line = lines[rolling_line_idx + 1] if rolling_line_idx + 1 < len(lines) else ""
        adv_map = {"kh1": "adv", "kl1": "dis"}
        adv = ""
        dice_type = first_roll_line.split(" ", 1)[0]
        for k, v in adv_map.items():
            if k in first_roll_line:
                adv = v
                dice_type = first_roll_line.replace(k, "").strip()
                break

        header = f"{player_name}: {user_text}{num_iterations}x {dice_type}"
        if adv:
            header += f"({adv})"
        bonus_match = re.search(r"([+-]\s*\d+)", first_roll_line)
        if bonus_match:
            header += f" {bonus_match.group(1)}"
        
        raw_rolls = lines[rolling_line_idx + 1:-1] if rolling_line_idx + 1 < len(lines) else []
        max_len = 0
        split_rolls = []
        for line in raw_rolls:
            if " + " in line:
                pre, post = line.split(" + ", 1)
                post = "+ " + post
            elif " = " in line:
                pre, post = line.split(" = ", 1)
                post = "= " + post
            else:
                pre, post = line, ""
            split_rolls.append((pre, post))
            max_len = max(max_len, self._visible_len(pre))

        roll_lines = []
        for idx, (pre, post) in enumerate(split_rolls, 1):
            pad_len = max_len - self._visible_len(pre)
            if post:
                roll_lines.append(f"{idx:02d}. {pre}{'&nbsp;'*pad_len} {post}".rstrip())
            else:
                roll_lines.append(f"{idx:02d}. {pre}".rstrip())

        return [header] + roll_lines + [lines[-1]]
    
    def _normalize_line(self, text: str) -> str:
        """Odstraní markdowny a převede některé značky na HTML."""
        text = text.strip()
        text = text.replace("`", "")
        text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
        for prefix in ("**result**:", "**total**:"):
            if text.lower().startswith(prefix):
                text = text.split(":", 1)[1].strip()
                break
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        text = re.sub(r"__(.*?)__", r"<u>\1</u>", text)
        text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
        return text
        
    def _visible_len(self, s: str) -> int:
        """Vrátí délku textu bez HTML tagů a entit."""
        clean = re.sub(r"<[^>]*>", "", s)
        clean = clean.replace("&nbsp;", " ")
        return len(clean)

    
    
class ImageQueue:
    def __init__(self, interval, panel, sio):
        self.interval = interval
        self.panel = panel
        self.sio = sio

        self.images_queue = deque()
        self.deletion_queue = asyncio.Queue()
        self.running = True
        asyncio.create_task(self._print_image())
        asyncio.create_task(self._process_deletions())

    def add_url_list(self, urls):
        """Přidá seznam čistých URL adres do fronty"""
        for url in urls:
            self.images_queue.append(url)
            logger.debug(f"URL image added to queue: {url}")

    def add_images(self, attachments):
        """Přidá nové obrázky do fronty"""
        for att in attachments:
            if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', ".bmp"]):
                self.images_queue.append(att.url)
                
    async def _print_image(self):
        """Postupně po jednom posílá obrázky z fronty přes socket"""
        while self.running:
            if self.images_queue:
                image = self.images_queue.popleft()
                await self.sio.emit("new_image", {
                    "panel": self.panel, 
                    "url": image, 
                        })
                logger.debug(f"Img sent - {image} to {self.panel}")
                await asyncio.sleep(self.interval)
                # Schedule deletion
                filename = image.split('/')[-1]
                await self.deletion_queue.put(filename)
                if not self.images_queue:
                    await self.sio.emit("new_image", {
                        "panel": self.panel, 
                        "url": "", 
                    })
                    logger.debug("Img deleted")
            else:
                await asyncio.sleep(1)
        
    async def _process_deletions(self):
        """Process deletion queue in a single task."""
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    filename = await self.deletion_queue.get()
                    async with session.delete(f"http://127.0.0.1:8080/images-storage/{filename}") as response:
                        if response.status == 204:
                            logger.debug(f"Image deleted from memory: {filename}")
                        else:
                            logger.debug(f"Failed to delete image {filename}: {response.status}")
                    self.deletion_queue.task_done()
                except Exception as e:
                    logger.debug(f"Failed to delete image: {e}")        
        
class ChannelWatcher:
    def __init__(self, client, config, sio):
        self.client = client
        self.config = config
        self.sio = sio
        
        self.channel_id = str(config.get("channel_id", "Unknown"))
        self.socket_panel = config.get("socket_panel", "panel-a")
        self.image_panel = config.get("image_panel", self.socket_panel)
        self.file_path = config.get("file_path", "output.txt")
        self.interval = config.get("interval", 10)
        self.type_output = config.get("type_output", "socket")
        self.manual_clear = config.get("manual_clear", True)
        self.gui_watcher = config.get("gui_watcher", False)
        self.ignore_mode = config.get("ignore_mode", None)
        self.comment = config.get("comment", "uncommented")

        self.active_messages = []  # List dicts: {"id": int, "msg_obj": obj, "expiry": float}
        self.running = False
        self._lock = asyncio.Lock()

        dispatcher.register(self.channel_id, self)
        logger.debug(f"Watcher {self.channel_id} (Panel: {self.socket_panel}) created and registred.")

    async def start(self):
        self.running = True
        if self.image_panel is not None:
            self.images = ImageQueue (self.interval, self.image_panel, self.sio)
        if self.socket_panel is not None:
            self.formatter = MessageFormatter(self.config)
            if not self.manual_clear:
                asyncio.create_task(self._auto_clear_loop())
                logger.debug(f"Watcher for channel {self.channel_id} run TTL loop.")
            await self._refresh_display()
        logger.info(f"Watcher ({self.comment}) for channel {self.channel_id} (Panel: {self.socket_panel}) started.")

    async def on_new_message(self, message):
        """Volá se při nové zprávě z Discordu."""
        if self.ignore_mode == "bot" and message.author.bot:
            return
        if self.ignore_mode == "humans" and not message.author.bot:
            return
        if message.content.startswith('!'):
            return
        
        async with self._lock:
            self.is_content = True
            if self.image_panel is not None:
                found_urls = self._remove_url(message)
                
                if found_urls:
                    self.images.add_url_list(found_urls)
               
                if message.attachments:
                    self.images.add_images(message.attachments)
                    logger.debug("Img received")

            if self.socket_panel is not None and self.is_content:
                logger.debug(f"Content for text panel = {message.content}")
                self._cleanup_expired_messages()          

                expiry = time.time() + self.interval
                self.active_messages.append({
                    "id": message.id,
                    "msg_obj": message,
                    "expiry": expiry
                })
                logger.debug(f"New message added: {message.id} from {message.author} (expire time {self.interval}s)")
                await self._refresh_display()

    async def on_message_edit(self, message):
        """Aktualizace existující zprávy bez resetu času."""
        async with self._lock:
            for m in self.active_messages:
                if m["id"] == message.id:
                    if self.image_panel is not None:
                        self._remove_url(message)
                    m["msg_obj"] = message
                    logger.debug(f"message {message.id} edited.")
                    await self._refresh_display()
                    break

    async def on_manual_input(self, text, author="Manual", attachments=None):
        """Vytvoření falešného objektu pro manuální vstup z GUI."""
        if attachments is None:
            attachments = []
        mock_msg = SimpleNamespace(
            id=int(time.time() * 1000),
            content=text,
            author=SimpleNamespace(name=author, display_name=author, bot=False),
            mentions=[],
            attachments=attachments
        )
        logger.debug(f"Manual input from {author}: {text}")
        await self.on_new_message(mock_msg)

    def _remove_url(self, message):
        url_pattern = r'(https?://\S+\.(?:png|jpg|jpeg|gif|webp|bmp))'
        found_urls = re.findall(url_pattern, message.content, re.IGNORECASE)
        
        if found_urls:
            logger.debug(f"Content s URL = {message.content}")
            message.content = re.sub(url_pattern, '', message.content).strip()
            logger.debug(f"Content bez URL = {message.content}")
            c = re.sub(" ", "", message.content).strip()
            if c == "":
                self.is_content = False
        return found_urls

    async def clear_content(self):
        """Logika pro klávesu 'd' (Smart Clear)."""
        if self.socket_panel is None:
            return
        async with self._lock:
            removed_count = self._cleanup_expired_messages()
            if removed_count == 0:
                logger.warning(f"No expare messages ({self.comment}).")
            else:
                await self._refresh_display()
                logger.info(f"Removed {removed_count} expire messages ({self.comment}).")

    def _cleanup_expired_messages(self):
        """Filtruje expirované zprávy z active_messages a vrací počet odstraněných."""
        now = time.time()
        old_count = len(self.active_messages)
        self.active_messages = [m for m in self.active_messages if m["expiry"] > now]
        return old_count - len(self.active_messages)

    async def _auto_clear_loop(self):
        """Smyčka, která hlídá automatické mazání po čase."""
        while self.running:
            async with self._lock:
                removed_count = self._cleanup_expired_messages()
                if removed_count > 0:
                    await self._refresh_display()
            await asyncio.sleep(1)

    async def _refresh_display(self):
        """Sestavení zpráv a odeslání do OBS/Souboru."""
        logger.debug(f"Watcher {self.channel_id}: refresh display with {len(self.active_messages)} active messages.")
        objs = [m["msg_obj"] for m in self.active_messages]
        
        formatted_messages = self.formatter.format_messages(objs)
        
        if self.type_output in ("socket", "both"):    
            await self.sio.emit("new_message", {
                "panel": self.socket_panel,
                "messages": formatted_messages
            })
            logger.debug(f"Watcher {self.channel_id}: sent {len(formatted_messages)} messages on panel {self.socket_panel} trough Socket.io.")

        if self.type_output in ("txt", "both"): 
            self._write_to_file(formatted_messages)

    def _write_to_file(self, lines):
        lines_for_file = []
        for msg in lines:
            for line in msg["content"] if isinstance(msg["content"], list) else [msg["content"]]:
                clean = re.sub(r"<s>(.*?)</s>", r"-\1-", line)
                clean = re.sub(r"<[^>]*>", "", clean)
                clean = clean.replace("&nbsp;", " ")
                lines_for_file.append(clean)
        """Uloží zprávu do souboru"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines_for_file))
        except Exception as e:
            logger.error(f"Error due to write to file: {e}")