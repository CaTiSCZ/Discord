import discord
import asyncio
import os
import re
import textwrap
from dotenv import load_dotenv

load_dotenv("personal_data.env")

FILE_PATH = os.getenv("FILE_PATH", "rolls.txt")
LAST_ID_FILE = os.getenv("LAST_ID_FILE", "log_file.txt" )
INTERVAL = 15
HISTORY_LIMIT = 10

try:
    TOKEN = os.environ["TOKEN"]
except KeyError:
    raise ValueError("Chybí TOKEN v personal_data.env")
try:
    CHANNEL_ID = int(os.environ["CHANNEL_ID"])
except KeyError:
    raise ValueError("Chybí CHANNEL_ID v personal_data.env")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

last_message_id: int | None = None
empty_written: bool = False
no_new_messages_count: int = 0

def load_last_id():
    if os.path.exists(LAST_ID_FILE):
        try:
            with open(LAST_ID_FILE, "r") as f:
                return int(f.read().strip())
        except:
            return None
    return None

def save_last_id(msg_id: int):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(msg_id))

def format_columns_all(content_lines, max_rows_per_col=9, max_col_width=40, col_spacing=2):
    #Zalomí dlouhé řádky, rozdělí řádky do sloupců pro lepší čitelnost, 9 řádků na sloupec, 40 znaků šířka sloupce, 2 mezery mezi sloupci
    #sloupce se vyrovnají podle nejdelšího řádku v daném sloupci
    wrapped_lines = []
    for line in content_lines:
        wrapped_lines.extend(textwrap.wrap(line, width=max_col_width, break_long_words=False) or [""])
    n = len(wrapped_lines)
    if n <= max_rows_per_col:
        return wrapped_lines
    num_cols = (n + max_rows_per_col - 1) // max_rows_per_col
    cols = []
    for c in range(num_cols):
        start = c * max_rows_per_col
        end = min(start + max_rows_per_col, n)
        cols.append(wrapped_lines[start:end])
    col_widths = [min(max(len(line) for line in col), max_col_width) for col in cols]
    max_len = max(len(col) for col in cols)
    for col in cols:
        while len(col) < max_len:
            col.append("")
    output_lines = []
    for i in range(max_len):
        row = ""
        for col, width in zip(cols, col_widths):
            row += col[i].ljust(width + col_spacing)
        output_lines.append(row.rstrip())
    return output_lines

def parse_dice_info(text):
    dice_match = re.search(r"(\d+d\d+(?:kh1|kl1)?)", text)
    dice_type = dice_match.group(1) if dice_match else "None"
    bonus_match = re.search(r"([+-]\s*\d+)", text)
    bonus = bonus_match.group(1).replace(" ", "") if bonus_match else ""
    adv_map = {"kh1": "adv", "kl1": "dis"}
    adv = ""
    dice_type_display = dice_type
    for k, v in adv_map.items():
        if k in dice_type:
            adv = v
            dice_type_display = dice_type.replace(k, "").strip()
            break
    return adv, dice_type_display, bonus

def parse_single_roll(lines):
    player_line, roll_line, total_line = lines
    player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"
    roll_line = normalize_roll_line(roll_line)
    total_value = normalize_roll_line(total_line)
    if total_value:
        roll_line += f" = {total_value}"
    return [f"{player_name} - {roll_line.strip()}"]

def parse_multi_roll(lines):
    player_line = lines[0]
    player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"
    rolling_line_idx = next((i for i,l in enumerate(lines) if "Rolling" in l), 1)
    rolling_line = lines[rolling_line_idx]
    user_text = rolling_line.split(":", 1)[0].strip() if ":" in rolling_line else ""
    iter_match = re.search(r"(\d+)\s*iterations", rolling_line, re.IGNORECASE)
    num_iterations = int(iter_match.group(1)) if iter_match else 1
    first_roll_line = lines[rolling_line_idx + 1]
    adv, dice_type, bonus = parse_dice_info(first_roll_line)
    plural = f"{num_iterations}x " if num_iterations > 1 else ""
    header = f"{player_name} - {plural}{dice_type}"
    if adv:
        header += f"({adv.strip()})"
    if bonus:
        header += f" {bonus}"
    if user_text:
        header += f", {user_text}"
    roll_lines = []
    for i, line in enumerate(lines[rolling_line_idx+1:], 1):
        line = normalize_roll_line(line)
        if i == len(lines) - rolling_line_idx - 1:  # poslední řádek
            roll_lines.append(line)
        else:
            if line.strip():
                roll_lines.append(f"{i}. {line}")
    return [header] + roll_lines

def detect_roll_type_and_parse(lines):
    num_lines = len(lines)
    if num_lines == 3:
        return parse_single_roll(lines)
    elif num_lines >= 5:
        return parse_multi_roll(lines)
    else:
        return []
    
def normalize_roll_line(text: str) -> str:
    text = text.strip()
    text = text.replace("**", "").replace("__", "")
    for prefix in ("result:", "total:"):
        if text.lower().startswith(prefix):
            text = text.split(":", 1)[1].strip()
            break
    text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
    text = re.sub(r"~~(\d+)~~", r"-\1-", text)
    return text

@client.event
async def on_ready():
    global last_message_id
    print(f"Přihlášen jako {client.user}")
    last_message_id = load_last_id()
    if last_message_id:
        print(f"Načteno poslední ID zprávy: {last_message_id}")
    else:
        print("Nebylo nalezeno předchozí ID zprávy (první běh).")
    channel = client.get_channel(CHANNEL_ID)
    await monitor_channel(channel)

async def fetch_messages(channel: discord.TextChannel) -> list[discord.Message]:
    return [msg async for msg in channel.history(limit=HISTORY_LIMIT)]

async def process_messages(messages: list[discord.Message], last_id: int | None) -> tuple[list[str], int]:
    all_lines: list[str] = []
    newest_message = messages[0]
    if last_id is None:
        return all_lines, newest_message.id  # první běh
    for msg in messages:
        if msg.id == last_id:
            break
        content = msg.clean_content.strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if msg.author.bot:
            parsed = detect_roll_type_and_parse(lines)
            all_lines.extend(parsed)
        else:
            member = msg.guild.get_member(msg.author.id) or await msg.guild.fetch_member(msg.author.id)
            display_name = getattr(member, "display_name", msg.author.name)
            if content:
                all_lines.append(f"{display_name}: {content}")
    return all_lines, newest_message.id

async def monitor_channel(channel: discord.TextChannel):
    global last_message_id, empty_written, no_new_messages_count
    all_lines: list[str] = []
    while True:
        try:
            messages = await fetch_messages(channel)
            if not messages:
                await asyncio.sleep(INTERVAL)
                continue
            lines, newest_id = await process_messages(messages, last_message_id)
            if last_message_id is None:
                last_message_id = newest_id
                save_last_id(last_message_id)
                await asyncio.sleep(INTERVAL)
                continue
            if newest_id != last_message_id:
                no_new_messages_count = 0
                all_lines = lines
                if all_lines:
                    formatted = format_columns_all(all_lines)
                    with open(FILE_PATH, "w", encoding="utf-8") as f:
                        f.write("\n".join(formatted))
                    print("Nalezeny nové zprávy.")
                last_message_id = newest_id
                save_last_id(last_message_id)
                empty_written = False
            else:
                no_new_messages_count += 1
                if no_new_messages_count >= 2 and not empty_written:
                    open(FILE_PATH, "w", encoding="utf-8").close()
                    print("Žádné nové zprávy – soubor vyprázdněn.")
                    empty_written = True
        except Exception as e:
            print("Chyba monitor_channel:", e)
        sleep_time = INTERVAL
        if len(all_lines) > 14:
            sleep_time += min((max(len(all_lines) - 14, 0) + 6) // 7, 5) * 5
        await asyncio.sleep(sleep_time)


client.run(TOKEN)