# channel_watcher.py
import discord
import asyncio
import os
import re
import logging
from typing import List, Dict, Optional
import sys
import event

logger = logging.getLogger("DiscordWatcher.ChannelWatcher")

# -----------------------------------------------------------------------------
# MessageFormatter
# - odpovídá za normalizaci textu, parsing Avrae hodů,
#   zalamování, formátování do více sloupců a ukládání HTML.
# -----------------------------------------------------------------------------
class MessageFormatter:
    def __init__(
        self,
        max_rows_per_column: int = 9,
        max_column_width: int = 40,
        column_spacing: int = 2,
        show_author_mode: str = "both",  # "both", "human", "bot", False/None
        header_text: str = "",
        
    ):
        self.max_rows_per_column = max_rows_per_column
        self.max_column_width = max_column_width
        self.column_spacing = column_spacing
        self.show_author_mode = show_author_mode
        self.computed_width = 650  # výchozí šířka
        self.max_line_len = 0  # pro výpočet šířky
        self.event_save_html = event.Event()
        self.header_text = header_text


    # ----------------- pomocné -----------------
    @staticmethod
    def visible_len(s: str) -> int:
        """Vrátí délku textu bez HTML tagů a entit."""
        clean = re.sub(r"<[^>]*>", "", s)
        clean = clean.replace("&nbsp;", " ")
        return len(clean)

    def smart_wrap(self, text: str, width: int) -> List[str]:
        """Zalamuje text podle viditelné délky (ignoruje HTML tagy)."""
        words = text.split()
        lines = []
        current = ""
        current_len = 0
        for w in words:
            w_len = self.visible_len(w)
            if current_len + (1 if current else 0) + w_len > width:
                lines.append(current)
                current = w
                current_len = w_len
            else:
                if current:
                    current += " "
                    current_len += 1
                current += w
                current_len += w_len
        if current:
            lines.append(current)
        return lines or [""]

    def format_columns_all(self, content_lines: List[str]) -> List[str]:
        """Zformátuje řádky do column layoutu (převzato a upraveno z původního kódu)."""
        wrapped_lines = []
        if self.header_text:
            wrapped_lines.append(self.header_text)
        for line in content_lines:
            wrapped_lines.extend(self.smart_wrap(line, self.max_column_width))
        n = len(wrapped_lines)
        if n <= self.max_rows_per_column:
            # Jen jeden sloupec
            output_lines = wrapped_lines
            self.max_line_len = max((self.visible_len(line) for line in output_lines), default=0)
             
            return output_lines
        # Více sloupců
        num_cols = (n + self.max_rows_per_column - 1) // self.max_rows_per_column
        cols = []
        for c in range(num_cols):
            start = c * self.max_rows_per_column
            end = min(start + self.max_rows_per_column, n)
            cols.append(wrapped_lines[start:end])
        col_widths = [min(max(self.visible_len(line) for line in col), self.max_column_width) for col in cols]
        max_len = max(len(col) for col in cols)
        for col in cols:
            while len(col) < max_len:
                col.append("")
        output_lines = []
        for i in range(max_len):
            row = ""
            for col, width in zip(cols, col_widths):
                line = col[i]
                pad_len = width - self.visible_len(line)
                row += line + (" " * (pad_len + self.column_spacing))
            output_lines.append(row.rstrip())
        
        return output_lines

    # ----------------- normalizace -----------------
    def normalize_line(self, text: str, txt_output:bool = False) -> str:
        """Odstraní markdowny a převede některé značky na HTML."""
        text = text.strip()
        text = text.replace("__", "").replace("`", "")
        text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
        for prefix in ("**result**:", "**total**:"):
            if text.lower().startswith(prefix):
                text = text.split(":", 1)[1].strip()
                break
        if txt_output:
            text = re.sub(r"~~(.*?)~~", r"-\1-", text)
            text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
            text = re.sub(r"\*(.*?)\*", r"\1", text)
            return text
        
        # markdown -> HTML (basic)
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        return text

    # ----------------- Avrae parsing (single/multi roll) -----------------
    @staticmethod
    def parse_single_roll(lines: List[str], author: str) -> List[str]:
        """Parse single roll (3 lines): player, rollline, total"""
        try:
            player_line, roll_line, total_value = lines
            
        except ValueError:
            return []
        player_name = author
        return [f"{player_name}: {roll_line.strip()} = {total_value.strip()}"]

    @staticmethod
    def parse_multi_roll(lines: List[str], author: str) -> List[str]:
        """
        Parse multi roll (≥5 lines). Vrací hlavičku a jednotlivé řádky s číslováním.
        Implementace věrná původní logice.
        """
        if not lines:
            return []
        
        player_name = author

        rolling_line_idx = next((i for i, l in enumerate(lines) if "Rolling" in l), 1)
        rolling_line = lines[rolling_line_idx]
        user_text = rolling_line.split(":", 1)[0].strip() if ":" in rolling_line else ""

        iter_match = re.search(r"(\d+)\s*iterations", rolling_line, re.IGNORECASE)
        num_iterations = int(iter_match.group(1)) if iter_match else 1

        first_roll_line = lines[rolling_line_idx + 1] if rolling_line_idx + 1 < len(lines) else ""
        adv_map = {"kh1": "adv", "kl1": "dis"}
        adv = ""
        dice_type = first_roll_line
        for k, v in adv_map.items():
            if k in first_roll_line:
                adv = v
                dice_type = first_roll_line.replace(k, "").strip()
                break

        plural = f"{num_iterations}x " if num_iterations > 1 else ""
        header = f"{player_name}: {plural}{dice_type}"
        if adv:
            header += f"({adv})"
        bonus_match = re.search(r"([+-]\s*\d+)", first_roll_line)
        if bonus_match:
            header += f" {bonus_match.group(1)}"
        if user_text:
            header += f", {user_text}"

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
            max_len = max(max_len, MessageFormatter.visible_len(pre))

        roll_lines = []
        for idx, (pre, post) in enumerate(split_rolls, 1):
            pad_len = max_len - MessageFormatter.visible_len(pre)
            if post:
                roll_lines.append(f"{idx:02d}. {pre}{'&nbsp;'*pad_len} {post}".rstrip())
            else:
                roll_lines.append(f"{idx:02d}. {pre}".rstrip())

        return [header] + roll_lines + [lines[-1]]

    def detect_roll_type_and_parse(self, lines: List[str], author: str) -> List[str]:
        """Rozhodne, jestli jde o single/multi roll a zavolá parser."""
        num_lines = len(lines)
        if num_lines == 3:
            return self.parse_single_roll(lines, author)
        elif num_lines >= 5:
            return self.parse_multi_roll(lines, author)
        return []

    # ----------------- render do HTML -----------------
    def save_html(self, all_lines: List[str], file_path: str, txt_output: bool = False):
        """Uloží HTML file. all_lines jsou už normalized a připravené."""
        self.max_line_len = max((self.visible_len(line) for line in all_lines), default=0)
        self.event_save_html.emit(file_path, self.max_line_len)
        if txt_output:
            self.save_txt(all_lines, file_path)
            return
        html_lines = "\n".join(all_lines)
        html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="1">
<title>Rolls</title>
<style>
body {{
    background-color: #000000;
    color: #ffffff;
    font-family: monospace;
    padding: 0px;
    margin: 0px;
    overflow: visible;
    white-space: pre;
    font-size: 31px;
}}
pre {{
    margin: 0;
    padding: 0;
    line-height: 1.2;
}}
b {{ font-weight: bold; }}
i {{ font-style: italic; }}
s {{ text-decoration: line-through; }}
</style>
</head>
<body><pre>{html_lines}</pre></body>
</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    def save_txt(self,all_lines: List[str], file_path: str):
        """Uloží TXT file. all_lines jsou už normalized a připravené."""
        all_lines = [line.replace("&nbsp;", " ") for line in all_lines]
        txt_lines = "\n".join(all_lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(txt_lines)
        
# -----------------------------------------------------------------------------
# ChannelWatcher
# - hlavní logika: načítání, cache, detekce změn, mazání (auto/manual), listener
# -----------------------------------------------------------------------------
class ChannelWatcher:
    def __init__(
        self,
        client: discord.Client,
        channel_id: int,
        file_path: str,
        last_id_file: str,
        interval: int = 10,
        history_limit: int = 10,
        show_author_mode: str = "both",  # "both", "human", "bot", False/None
        ignore_mode: Optional[str] = None,  # "bot", "human", None
        manual_clear: bool = False,
        max_rows_per_column: int = 9,
        max_column_width: int = 40,
        column_spacing: int = 2,
        txt_output: bool = False,
        header_text: str = "",
    ):
        # parametry
        self.client = client
        self.loop = asyncio.get_event_loop()
        self.channel_id = channel_id
        self.file_path = file_path
        self.last_id_file = last_id_file
        self.interval = interval
        self.history_limit = history_limit
        self.show_author_mode = show_author_mode
        self.ignore_mode = ignore_mode
        self.manual_clear = manual_clear
        self.txt_output = txt_output
        self.header_text = header_text

        # formatter instance (řeší celý rendering & parsing)
        self.formatter = MessageFormatter(
            max_rows_per_column=max_rows_per_column,
            max_column_width=max_column_width,
            column_spacing=column_spacing,
            show_author_mode=show_author_mode, header_text=header_text,
        )

        # stav
        self.old_last_id: Optional[int] = None
        self.last_id: Optional[int] = None
        
        self.cache: List[Dict] = []
        self.running = True
        self.file_empty = False
        self.manual_delete_allowed = False

    # ----------------- práce se souborem last_id -----------------
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

    # ----------------- fetch / normalizace surových zpráv -----------------
    async def fetch_recent(self, channel: discord.TextChannel) -> List[discord.Message]:
        """
        Stáhne posledních `history_limit` zpráv z kanálu (nejnovější).
        Vrací se seřazené od starších k novějším (asc).
        """
        try:
            msgs = [msg async for msg in channel.history(limit=self.history_limit)]
            msgs.sort(key=lambda m: m.created_at)
            #print(f"[FETCH] Staženo {len(msgs)} posledních zpráv (limit={self.history_limit}).")
            return msgs
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            return []

    async def normalize_msg_obj(self, msg: discord.Message) -> Dict:
        """Vytvoří surovou reprezentaci zprávy: id, author (display_name), content."""
        try:
            member = msg.guild.get_member(msg.author.id) or await msg.guild.fetch_member(msg.author.id)
            display_name = getattr(member, "display_name", msg.author.name)
        except Exception:
            display_name = msg.author.display_name if hasattr(msg.author, "display_name") else msg.author.name
        author_name = re.sub(r"\s*\([^)]*\)\s*$", "", display_name)
        is_avrae = msg.author.name.lower() == "avrae"

        if is_avrae:
            mentioned = msg.mentions[0] if msg.mentions else None
            if mentioned:
                member = msg.guild.get_member(mentioned.id) or await msg.guild.fetch_member(mentioned.id)
                author_name = re.sub(r"\s*\([^)]*\)\s*$", "", getattr(member, "display_name", member.name))
            else:
                author_name = "hráč"
            
            
        return {
            "id": msg.id,
            "author": author_name,
            "content": msg.clean_content.strip(),
            "is_bot": msg.author.bot,  # přidáme rovnou flag
            "is_from_avrae": msg.author.name == "Avrae",
        }

    # ----------------- detekce nových / editovaných zpráv -----------------
    async def find_new_and_updates(self, recent: List[discord.Message]) -> Dict[str, List[Dict]]:
        """
        Recent jsou discord.Message (posledních N). Vrátí dict s 'added' a 'edited' (surové dicty).
        - 'added' jsou zprávy s ID > last_id (nebo když last_id je None => všechny)
        - 'edited' jsou zprávy, které mají stejné ID jako v cache, ale liší se content
        """
        recent_norm = [await self.normalize_msg_obj(m) for m in recent]
        added = []
        edited = []
        cache_by_id = {m["id"]: m for m in self.cache}

        for m in recent_norm:
            # ignore podle ignore_mode
            # pozor: recent_norm nemá info o tom, zda author bot; můžeme zjistit přes m["author"]? Ne.
            # proto ignor_mode vyhodnocujeme dříve - ale pro jednoduchost: pokud ignore_mode nastaveno,
            # nemůžeme zjistit bot/human z normované struktury. Tudíž zavoláme původní Message objekt v recent
            # a zkontrolujeme tam. To znamená, že tady voláme normalize už jen pro comparaci obsahu.
            if self.ignore_mode in ("bot", "human"):
                # find original message to inspect .author.bot
                orig = next((x for x in recent if x.id == m["id"]), None)
                if orig:
                    if self.ignore_mode == "bot" and orig.author.bot:
                        continue
                    if self.ignore_mode == "human" and not orig.author.bot:
                        continue

            if self.last_id:
                if m["id"] > self.last_id:
                    added.append(m)
            else:
                # pokud last_id není nastaveno (první start), vezmeme všechny jako added
                added.append(m)

            # edited: pokud je v cache a obsah se liší
            c = cache_by_id.get(m["id"])
            if c and c["content"] != m["content"]:
                edited.append(m)

        # sort added by id (ascending)
        added.sort(key=lambda x: x["id"])

        return {"added": added, "edited": edited}

    # ----------------- aktualizace cache a správa věku -----------------
    def integrate_changes(self, added, edited):
        if not added and not edited:
            # nic nového → nic nepřepisujeme
            return
        # přidáme nové zprávy
        if self.old_last_id:
            self.cache = [m for m in self.cache if m["id"] > self.old_last_id] 
        for msg in added:
            if not any(c["id"] == msg["id"] for c in self.cache):
                self.cache.append({
                    "id": msg["id"],
                    "author": msg["author"],
                    "content": msg["content"],
                })

        # upravíme editované zprávy
        for msg in edited:
            for c in self.cache:
                if c["id"] == msg["id"]:
                    c["content"] = msg["content"]

        # aktualizuj last_id jen pokud máme nové
        if added:
            self.old_last_id = self.last_id
            self.last_id = added[-1]["id"]
            self.save_last_ids()

        #print(f"[CACHE] Aktualizováno: cache_size={len(self.cache)}")

    # ----------------- příprava textů pro rendering (včetně Avrae parsing) -----------------
    def prepare_render_lines(self) -> List[str]:
        """
        Vytvoří finální seznam řádků (stringů) z cache.
        - provede normalize_line přes formatter
        - pokud zpráva pochází od Avrae (bot jméno "Avrae"), použije se parsing
          pozn.: pro to bychom potřebovali uložit také flag is_bot a author.name při normování.
        """
        lines = []
        for item in self.cache:
            content = item.get("content", "")
            author = item.get("author", "Unknown")
            is_bot = item.get("is_bot", False)
            
            # provést normalizaci (markdown -> HTML)
            content_lines = [self.formatter.normalize_line(l, self.txt_output) for l in content.splitlines()]
            if not content_lines:
                continue

            # pokud to vypadá jako Avrae (heuristika): začíná "@" v první lince a bot generuje víceřádkový výstup,
            # bohužel v cache už nemáme originální msg.author.name (bot) - můžeme rozšířit cache o is_bot flag
            # Proto: pokud item obsahuje key 'is_from_avrae', použij parser.
            if item.get("is_from_avrae"):
                parsed = self.formatter.detect_roll_type_and_parse(content_lines, author)
                if parsed:
                    content_lines = parsed 
           

            show_author = False
            if self.show_author_mode == "both":
                show_author = True
            elif self.show_author_mode == "human" and not is_bot:
                show_author = True
            elif self.show_author_mode == "bot" and is_bot:
                show_author = True
            elif not self.show_author_mode:
                show_author = False

            # první řádek s autorem (pokud povoleno)
            if show_author:
                lines.append(f"{author}: {content_lines[0]}")
            else:
                lines.append(content_lines[0])

            # ostatní řádky odsazené
            if show_author and len(content_lines) > 1:
                indent = " " * (len(author) + 2)
                for l in content_lines[1:]:
                    # neodstranit začátek řádku – mezery se přidají z indentu
                    lines.append(f"{indent}{l}")
            elif len(content_lines) > 1:
                lines.extend(content_lines[1:])
                
        return self.formatter.format_columns_all(lines)

    # ----------------- pomoc pro načtení is_bot / is_from_avrae do cache -----------------
    def enrich_cache_items_from_recent(self, recent_msgs: List[discord.Message]):
        """
        Synchronizuje doplňující info (is_bot, is_from_avrae) do položek cache
        podle id. Toto zabezpečí, že víme, které položky pochází od bota Avrae.
        """
        by_id = {m.id: m for m in recent_msgs}
        for item in self.cache:
            orig = by_id.get(item["id"])
            if orig:
                item["is_bot"] = orig.author.bot
                # jednoduchá heuristika: Avrae má jméno "Avrae"
                try:
                    item["is_from_avrae"] = orig.author.name == "Avrae"
                except Exception:
                    item["is_from_avrae"] = False
            else:
                # pokud nedostaneme originální obj (protože nebyl ve stažených recent),
                # necháme předešlé hodnoty nebo False
                item.setdefault("is_bot", False)
                item.setdefault("is_from_avrae", False)

    # ----------------- hlavní cyklus (jeden běh) -----------------
    async def run_cycle(self, channel: discord.TextChannel):
        def save_changes(added, edited, recent_msgs):
            self.integrate_changes(added, edited)
            self.enrich_cache_items_from_recent(recent_msgs)
            lines = self.prepare_render_lines()
            self.formatter.save_html(lines, self.file_path, self.txt_output)
            self.file_empty = False
            self.manual_delete_allowed = False  
            logger.debug(f"{self.file_path} changed.")
            return lines
        try:
            recent_msgs = await self.fetch_recent(channel)
            result = await self.find_new_and_updates(recent_msgs)
            added = result["added"]
            edited = result["edited"]


            if added or edited:
                # nové zprávy → aktualizuj cache a HTML
                save_changes(added, edited, recent_msgs)
                self.last_id = added[-1]["id"] if added else self.last_id
                return
            
            if self.manual_clear and not self.manual_delete_allowed and not self.file_empty:
                self.manual_delete_allowed = True
                logger.info(f"Manual clear {self.file_path} allowed.")

            if not self.manual_clear:
                # žádné nové zprávy → vyčisti HTML jen jednou
                if self.cache:
                    self.cache.clear()
                    self.old_last_id = self.last_id
                    self.formatter.save_html([], self.file_path, self.txt_output)
                    self.file_empty = True
                    logger.debug(f"No new message, {self.file_path} is cleared")
                return

        except Exception as e:
            logger.error(f"run_cycle selhal: {e}")

    # ----------------- listener pro manuální mazání -----------------
    
    def on_keypress(self, key: str):
        if key == "d" and self.manual_delete_allowed and not self.file_empty:
            logger.debug(f"{self.file_path} is cleared")
            self.cache = []
            self.file_empty = True
            self.formatter.save_html([], self.file_path, self.txt_output)
            self.manual_delete_allowed = False

    # ----------------- hlavní smyčka -----------------
    async def run(self):
        """Hlavní smyčka, která spouští cykly."""
        channel = self.client.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Channel {self.channel_id} not responding (get_channel returned None).")
            return
        logger.info(f"Watch channel: {channel.name}")
        self.load_last_ids()
        if self.txt_output:
            self.file_path = self.file_path.replace(".html", ".txt")
        while self.running:
            await self.run_cycle(channel)
            await asyncio.sleep(self.interval)
        

# --- Samostatné spuštění souboru ---
if __name__ == "__main__":
    """
    Pokud je tento soubor spuštěn přímo (např. python channel_watcher.py),
    automaticky se místo toho spustí hlavní skript main_client.py,
    který zajišťuje vytvoření Discord klienta, listeneru a všech watcherů.
    """
    import subprocess


    script_path = os.path.join(os.path.dirname(__file__), "config_gui.py")
    print(f"⚙️ Spouštím hlavní skript: {script_path}")
    try:
        subprocess.run([sys.executable, script_path])
    except Exception as e:
        print(f"🛑 Nepodařilo se spustit config_gui.py: {e}")