# channel_watcher.py
import discord
import asyncio
import os
import re
import html
import sys
import msvcrt


class ChannelWatcher:
    """
    Sleduje jeden Discord kanál a zapisuje jeho obsah do HTML souboru.
    Umožňuje konfigurovat chování: ignorovat boty, zobrazovat autory, detekovat hody kostkou atd.
    """

    def __init__(
        self,
        client: discord.Client,
        channel_id: int,
        file_path: str,
        last_id_file: str,
        *,
        ignore_bots: bool = True,
        show_author: bool = True,
        auto_clear: bool = True,
        manual_clear: bool = True,
        format_mode: str = "simple",  # "simple" nebo "dice"
        interval: float = 10.0,
        history_limit: int = 10,
        font_size: int = 31,
        max_width_chars: int = 38,
        min_width_px: int = 650,
        px_per_char: int = 18,
    ):
        self.client = client
        self.channel_id = channel_id
        self.file_path = file_path
        self.last_id_file = last_id_file
        self.ignore_bots = ignore_bots
        self.show_author = show_author
        self.auto_clear = auto_clear
        self.manual_clear = manual_clear
        self.format_mode = format_mode
        self.interval = interval
        self.history_limit = history_limit
        self.font_size = font_size
        self.max_width_chars = max_width_chars
        self.min_width_px = min_width_px
        self.px_per_char = px_per_char

        self.last_message_id: int | None = None
        self.messages_cache: dict[int, str] = {}
        self.delete_enabled = False
        self.idle_cycles = 0
        self.last_state = None  # 'idle' nebo 'new'

    # ========== INTERNÍ METODY ==========

    def _load_last_id(self):
        if os.path.exists(self.last_id_file):
            try:
                return int(open(self.last_id_file, "r").read().strip())
            except ValueError:
                return None
        return None

    def _save_last_id(self, msg_id: int):
        with open(self.last_id_file, "w") as f:
            f.write(str(msg_id))

    async def _fetch_messages(self, channel: discord.TextChannel, after_id: int | None = None):
        """Načte zprávy po ID (pokud je dáno), jinak posledních N."""
        if after_id:
            messages = [msg async for msg in channel.history(limit=None, after=discord.Object(id=after_id))]
        else:
            messages = [msg async for msg in channel.history(limit=self.history_limit)]
        messages.sort(key=lambda m: m.created_at)
        return messages

    # ========== FORMÁTOVÁNÍ TEXTU ==========

    def _normalize_roll_line(self, text: str) -> str:
        """Převod markdownu na HTML a zkrášlení textu pro hody."""
        text = text.strip()
        text = text.replace("__", "").replace("`", "")
        text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
        for prefix in ("**result**:", "**total**:"):
            if text.lower().startswith(prefix):
                text = text.split(":", 1)[1].strip()
                break

        # převod markdownu
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        return text

    def _format_message(self, author, content):
        """Zpracuje zprávu podle zvoleného formátu."""
        if self.format_mode == "dice":
            content = self._normalize_roll_line(content)
        elif self.format_mode == "simple":
            content = html.escape(content)

        display_name = getattr(author, "display_name", author.name)
        if self.show_author:
            return f"{display_name}: {content}"
        return content

    def _wrap_html(self, lines: list[str]) -> str:
        """Zabalí obsah do HTML s jednotným stylem."""
        html_lines = "\n".join(lines)
        return f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="1">
<style>
body {{
    background-color: #000;
    color: #fff;
    font-family: monospace;
    white-space: pre;
    margin: 0;
    padding: 0;
    overflow: visible;
    font-size: {self.font_size}px;
}}
b {{ font-weight: bold; }}
i {{ font-style: italic; }}
s {{ text-decoration: line-through; }}
</style>
</head>
<body><pre>{html_lines}</pre></body>
</html>"""

    async def _regenerate_display(self, channel):
        """Znovu vygeneruje HTML ze všech známých zpráv."""
        all_lines = []
        for msg_id, content in self.messages_cache.items():
            msg = await channel.fetch_message(msg_id)
            if not msg or (self.ignore_bots and msg.author.bot):
                continue
            line = self._format_message(msg.author, content)
            all_lines.append(line)
        html_out = self._wrap_html(all_lines)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"💾 [{channel.name}] HTML aktualizováno ({len(all_lines)} řádků)")

    # ========== HLAVNÍ SLEDOVACÍ LOGIKA ==========

    async def start(self):
        """Spustí sledování daného kanálu."""
        channel = self.client.get_channel(self.channel_id)
        if not channel:
            print(f"❌ Kanál {self.channel_id} nenalezen!")
            return

        print(f"▶️ Sleduji kanál {channel.name} ({self.channel_id})")
        self.last_message_id = self._load_last_id()

        asyncio.create_task(self._monitor_channel(channel))
        if self.manual_clear:
            asyncio.create_task(self._keyboard_listener())

    async def _monitor_channel(self, channel: discord.TextChannel):
        """Pravidelně kontroluje nové zprávy."""
        while True:
            try:
                messages = await self._fetch_messages(channel, self.last_message_id)
                new_detected = False

                if messages:
                    for msg in messages:
                        if self.ignore_bots and msg.author.bot:
                            continue
                        content = msg.clean_content.strip()
                        if not content:
                            continue
                        self.messages_cache[msg.id] = content
                        new_detected = True

                    formatted = [
                        self._format_message(await self._get_author(channel, mid), txt)
                        for mid, txt in self.messages_cache.items()
                    ]
                    html_out = self._wrap_html(formatted)
                    with open(self.file_path, "w", encoding="utf-8") as f:
                        f.write(html_out)
                    self.last_message_id = messages[-1].id
                    self._save_last_id(self.last_message_id)

                # --- změna nebo klid ---
                if new_detected:
                    self.delete_enabled = False
                    self.idle_cycles = 0
                    if self.last_state != "new":
                        print(f"🆕 [{channel.name}] nové nebo změněné zprávy")
                        self.last_state = "new"
                else:
                    self.idle_cycles += 1
                    if self.last_state != "idle":
                        print(f"💤 [{channel.name}] žádná změna (soubor lze smazat klávesou)")
                        self.last_state = "idle"
                    if self.auto_clear and self.idle_cycles >= 2:
                        open(self.file_path, "w").close()
                        print(f"🗑️ [{channel.name}] soubor automaticky vymazán")

            except Exception as e:
                print(f"❌ [{channel.name}] chyba monitorování: {e}")

            await asyncio.sleep(self.interval)

    async def _get_author(self, channel, msg_id):
        """Vrátí objekt autora podle ID zprávy."""
        try:
            msg = await channel.fetch_message(msg_id)
            return msg.author
        except Exception:
            return None

    # ========== EDITACE ZPRÁV ==========

    async def on_message_edit(self, before, after):
        """Reakce na editaci zprávy."""
        if self.ignore_bots and after.author.bot:
            return
        self.messages_cache[after.id] = after.clean_content.strip()
        await self._regenerate_display(after.channel)
        print(f"✏️ [{after.channel.name}] zpráva {after.id} upravena")

    # ========== KLÁVESOVÉ MAZÁNÍ ==========

    async def _keyboard_listener(self):
        print(f"⌨️ [{self.channel_id}] libovolná klávesa = smazat, 'q' = konec")

        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch.lower() == 'q':
                    print("🔴 Ukončuji skript")
                    sys.exit(0)
                elif self.delete_enabled and os.path.exists(self.file_path):
                    os.remove(self.file_path)
                    print(f"🗑️ [{self.channel_id}] soubor ručně smazán")
            await asyncio.sleep(0.5)
