# channel_watcher.py
import discord
import asyncio
import os
import re

class ChannelWatcher:
    def __init__(
        self,
        client: discord.Client,
        channel_id: int,
        file_path: str,
        last_id_file: str,
        interval: int = 10,
        history_limit: int = 10,
        show_author_mode: str = "both", # "both", "human", "bot", "none"
        ignore_mode: str | None = None, # "bot", "human", nebo None
        manual_clear: bool = False,
        max_rows_per_column: int = 9,
        max_column_width: int = 40,
        column_spacing: int = 2,
    ):
        self.client = client
        self.channel_id = channel_id
        self.file_path = file_path
        self.last_id_file = last_id_file
        self.interval = interval
        self.history_limit = history_limit
        self.show_author_mode = show_author_mode
        self.ignore_mode = ignore_mode
        self.manual_clear = manual_clear
        self.max_rows_per_column = max_rows_per_column
        self.max_column_width = max_column_width
        self.column_spacing = column_spacing

        self.last_message_id: int | None = None  # ID poslední zpracované zprávy
        self.messages_cache: dict[int, str] = {}    # {msg_id: content}
        self.delete_enabled = False     # zda je povoleno mazání zpráv
        self.last_snapshot = {}     # {msg_id: content}
        self.last_state = None  # 'new' nebo 'idle'
        self.empty_written = False # zda byl již zapsán prázdný stav
        self.no_new_messages_count = 0 # počet cyklů bez nové zprávy
        self.message_max_age = 2  # kolik cyklů staré zprávy vydrží
        self.display_limit = 10   # maximální počet zpráv zobrazených najednou
        self.messages_cache: dict[int, dict] = {}  # {msg_id: {"content": str, "age": int}}
        self.message_ages: dict[int, int] = {}  # key = message id, value = počet cyklů
        self.manual_delete_ready: bool = False
        self.min_age_for_delete: int = 1  # minimální počet cyklů, než se může mazat


    # --- Pomocné funkce ---

    @staticmethod
    def visible_len(s: str) -> int:
        clean = re.sub(r"<[^>]*>", "", s)
        clean = clean.replace("&nbsp;", " ")
        return len(clean)

    @staticmethod
    def normalize_line(text: str) -> str:
        text = text.strip()
        text = text.replace("__", "").replace("`", "")
        text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
        for prefix in ("**result**:", "**total**:"):
            if text.lower().startswith(prefix):
                text = text.split(":", 1)[1].strip()
                break
        text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        return text

    def smart_wrap(self, text, width):
        words = text.split()
        lines, current = [], ""
        current_len = 0
        for w in words:
            w_len = self.visible_len(w)
            if current_len + (1 if current else 0) + w_len > width:
                lines.append(current)
                current, current_len = w, w_len
            else:
                if current:
                    current += " "
                    current_len += 1
                current += w
                current_len += w_len
        if current:
            lines.append(current)
        return lines or [""]

    def format_columns_all(self, content_lines):
        wrapped_lines = []
        for line in content_lines:
            wrapped_lines.extend(self.smart_wrap(line, self.max_column_width))
        n = len(wrapped_lines)
        if n <= self.max_rows_per_column:
            return wrapped_lines
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

    # --- HTML ---

    def save_html(self, all_lines: list[str]):
        html_lines = "\n".join(all_lines)
        html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="1">
<title>Discord výpis</title>
<style>
body {{
    background-color: #000;
    color: #fff;
    font-family: monospace;
    white-space: pre;
    font-size: 24px;
}}
</style>
</head>
<body><pre>{html_lines}</pre></body>
</html>
"""
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    # --- ID zpráv ---

    def load_last_id(self):
        if os.path.exists(self.last_id_file):
            try:
                return int(open(self.last_id_file, "r").read().strip())
            except ValueError:
                return None
        return None

    def save_last_id(self, msg_id: int):
        with open(self.last_id_file, "w") as f:
            f.write(str(msg_id))

    # --- Parsování hodů kostkou Avrae ---

    @staticmethod
    def parse_single_roll(lines):
        player_line, roll_line, total_value = lines
        player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"
        return [f"{player_name} - {roll_line.strip()} = {total_value.strip()}"]

    @staticmethod
    def parse_multi_roll(lines):
        player_line = lines[0]
        player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"

        rolling_line_idx = next((i for i, l in enumerate(lines) if "Rolling" in l), 1)
        rolling_line = lines[rolling_line_idx]
        user_text = rolling_line.split(":", 1)[0].strip() if ":" in rolling_line else ""

        iter_match = re.search(r"(\d+)\s*iterations", rolling_line, re.IGNORECASE)
        num_iterations = int(iter_match.group(1)) if iter_match else 1

        first_roll_line = lines[rolling_line_idx + 1]
        adv_map = {"kh1": "adv", "kl1": "dis"}
        adv = ""
        dice_type = first_roll_line
        for k, v in adv_map.items():
            if k in first_roll_line:
                adv = v
                dice_type = first_roll_line.replace(k, "").strip()
                break

        plural = f"{num_iterations}x " if num_iterations > 1 else ""
        header = f"{player_name} - {plural}{dice_type}"
        if adv:
            header += f"({adv})"
        bonus_match = re.search(r"([+-]\s*\d+)", first_roll_line)
        if bonus_match:
            header += f" {bonus_match.group(1)}"
        if user_text:
            header += f", {user_text}"

        # ostatní řádky
        raw_rolls = lines[rolling_line_idx + 1:-1]
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
            max_len = max(max_len, ChannelWatcher.visible_len(pre))

        roll_lines = []
        for idx, (pre, post) in enumerate(split_rolls, 1):
            pad_len = max_len - ChannelWatcher.visible_len(pre)
            if post:
                roll_lines.append(f"{idx:02d}. {pre}{'&nbsp;'*pad_len} {post}".rstrip())
            else:
                roll_lines.append(f"{idx:02d}. {pre}".rstrip())

        return [header] + roll_lines + [lines[-1]]

    @staticmethod
    def detect_roll_type_and_parse(lines):
        num_lines = len(lines)
        if num_lines == 3:
            return ChannelWatcher.parse_single_roll(lines)
        elif num_lines >= 5:
            return ChannelWatcher.parse_multi_roll(lines)
        return []
    
    async def listen_for_delete(self):
        while True:
            # pro Windows:
            import msvcrt
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key.lower() == b'd' and self.manual_delete_ready:
                    # smaž všechny zprávy, které splňují min_age_for_delete
                    to_delete = [mid for mid, m in self.messages_cache.items() if m["age"] >= self.min_age_for_delete]
                    for mid in to_delete:
                        del self.messages_cache[mid]
                    self.manual_delete_ready = False
            await asyncio.sleep(0.1)

    # --- Hlavní monitor kanálu ---

    async def monitor_channel(self):
        channel = self.client.get_channel(self.channel_id)
        self.last_message_id = self.load_last_id()
        print(f"📡 Sleduji kanál {channel.name} ({self.channel_id})")

        while True:
            try:
                messages = [msg async for msg in channel.history(limit=None, after=discord.Object(id=self.last_message_id))] \
                        if self.last_message_id else \
                        [msg async for msg in channel.history(limit=self.history_limit)]
                messages.sort(key=lambda m: m.created_at)

                cycle_lines = {}
                new_message_detected = False

                for msg in messages:
                    content = msg.clean_content.strip()

                    # --- filtrace zpráv ---
                    if hasattr(self, "ignore_mode"):
                        if self.ignore_mode == "bot" and msg.author.bot:
                            continue
                        if self.ignore_mode == "human" and not msg.author.bot:
                            continue
                    else:  # zpětná kompatibilita
                        if self.ignore_bot and msg.author.bot:
                            continue

                    # --- parsování Avrae hodů ---
                    if msg.author.bot and msg.author.name == "Avrae":
                        lines = [self.normalize_line(l) for l in content.splitlines() if l.strip()]
                        parsed = self.detect_roll_type_and_parse(lines)
                        for i, l in enumerate(parsed):
                            if i == len(parsed)-1 and l.startswith("total"):
                                cycle_lines[f"{msg.id}_{i}"] = l  # poslední řádek bez číslování
                            else:
                                cycle_lines[f"{msg.id}_{i}"] = l
                    else:
                        display_name = getattr(msg.author, "display_name", msg.author.name)
                        prefix = ""
                        if self.show_author_mode == "both":
                            prefix = f"{display_name}: "
                        elif self.show_author_mode == "human":
                            prefix = f"{display_name}: " if not msg.author.bot else ""
                        elif self.show_author_mode == "bot":
                            prefix = f"{display_name}: " if msg.author.bot else ""
                        # "none" → prefix zůstává ""

                        if content:
                            cycle_lines[msg.id] = prefix + self.normalize_line(content)

                    # --- detekce změn / aktualizace cache ---
                    if msg.id not in self.messages_cache:
                        # nová zpráva
                        self.messages_cache[msg.id] = {"content": content, "age": 0}
                        self.last_message_id = msg.id
                        new_message_detected = True
                    elif self.messages_cache[msg.id]["content"] != content:
                        # editovaná zpráva
                        self.messages_cache[msg.id]["content"] = content
                        self.messages_cache[msg.id]["age"] = 0  # reset věku, protože se změnila
                        self.last_message_id = msg.id
                        new_message_detected = True
                    else:
                        # stará zpráva, zvýšíme věk jen pokud nebyla znovu načtena
                        self.messages_cache[msg.id]["age"] += 1

                    # --- odstranění starých zpráv podle age a display_limit ---
                    # 1) zprávy přesáhly max_age
                    to_delete = [mid for mid, m in self.messages_cache.items() if m["age"] > self.message_max_age]
                    for mid in to_delete:
                        del self.messages_cache[mid]

                    # 2) zprávy, aby se vešly do display_limit
                    all_ids = list(self.messages_cache.keys())
                    if len(all_ids) > self.display_limit:
                        sorted_ids = sorted(all_ids, key=lambda mid: self.messages_cache[mid]["age"], reverse=True)
                        for mid in sorted_ids[self.display_limit:]:
                            del self.messages_cache[mid]

                    # --- zvýšení věku starých zpráv ---
                    for msg_id, msg_data in self.messages_cache.items():
                        if msg_id not in [m.id for m in messages]:  # nezvyšujeme věk znovu načtených
                            msg_data["age"] += 1

                    # --- kontrola, zda je možné manuální mazání ---
                    if not new_message_detected:
                        self.no_new_messages_count += 1
                        self.manual_delete_ready = any(
                            m["age"] >= self.min_age_for_delete for m in self.messages_cache.values()
                        )
                    else:
                        self.no_new_messages_count = 0
                        self.manual_delete_ready = False  # reset při nové zprávě

                    # --- odstranění zpráv podle max_age a display_limit ---
                    to_delete = [mid for mid, m in self.messages_cache.items() if m["age"] > self.message_max_age]
                    for mid in to_delete:
                        del self.messages_cache[mid]

                    all_ids = list(self.messages_cache.keys())
                    if len(all_ids) > self.display_limit:
                        sorted_ids = sorted(all_ids, key=lambda mid: self.messages_cache[mid]["age"], reverse=True)
                        for mid in sorted_ids[self.display_limit:]:
                            del self.messages_cache[mid]

                    # --- automatické mazání pokud nenastaveno manuální ---
                    if not new_message_detected and not self.manual_clear:
                        if self.no_new_messages_count >= 2:
                            self.messages_cache.clear()



                # --- ukládání do HTML ---
                if cycle_lines:
                    formatted = self.format_columns_all(list(cycle_lines.values()))
                    self.save_html(formatted)
                    self.empty_written = False
                else:
                    self.no_new_messages_count += 1
                    if self.no_new_messages_count >= 2 and not self.empty_written and not self.manual_clear:
                        open(self.file_path, "w", encoding="utf-8").close()
                        self.empty_written = True

            except Exception as e:
                print(f"❌ [{self.channel_id}] Chyba monitor_channel:", e)

            # --- dynamické prodloužení intervalu ---
            sleep_time = self.interval
            if len(cycle_lines) > self.max_rows_per_column:
                extend_time = 5
                max_column = 5
                sleep_time += min((len(cycle_lines) - self.max_rows_per_column + self.max_rows_per_column-1)//self.max_rows_per_column, max_column) * extend_time

            await asyncio.sleep(sleep_time)


    async def run(self):
        await asyncio.gather(
            self.monitor_channel(),
            self.listen_for_delete()
        )
