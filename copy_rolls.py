import discord
import asyncio
import os
import re
import textwrap
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
FILE_PATH = os.getenv("FILE_PATH", "rolls.txt")
LAST_ID_FILE = os.getenv("LAST_ID_FILE", "log_file.txt" )
INTERVAL = 15
HISTORY_LIMIT = 10

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

last_message_id = None
empty_written = False
no_new_messages_count = 0

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
    if "kh1" in dice_type:
        dice_type_display = dice_type.replace("kh1", "").strip()
        adv = "adv "
    elif "kl1" in dice_type:
        dice_type_display = dice_type.replace("kl1", "").strip()
        adv = "dis "
    else:
        dice_type_display = dice_type
        adv = ""
    return adv, dice_type_display, bonus

def parse_single_roll(lines):
    player_line, roll_line, total_line = lines
    player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"
    roll_line = normalize_roll_line(roll_line)
    total_match = re.search(r"Total:\s*(\d+)", total_line)
    total_value = total_match.group(1) if total_match else ""
    if total_value:
        roll_line += f" = {total_value}"
    return [f"{player_name} - {roll_line}"]

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
    if text.lower().startswith("result:"):
        text = text.split(":", 1)[1].strip()
    text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
    text = re.sub(r"~~(\d+)~~", r"-\1-", text)

    return text

@client.event
async def on_ready():
    global last_message_id
    print(f"✅ Přihlášen jako {client.user}")
    last_message_id = load_last_id()
    if last_message_id:
        print(f"📂 Načteno poslední ID zprávy: {last_message_id}")
    else:
        print("📂 Nebylo nalezeno předchozí ID zprávy (první běh).")
    channel = client.get_channel(CHANNEL_ID)
    await monitor_channel(channel)

async def monitor_channel(channel):
    global last_message_id, empty_written, no_new_messages_count
    all_lines = []
    while True:
        try:
            messages = [msg async for msg in channel.history(limit=HISTORY_LIMIT)]
            if not messages:
                await asyncio.sleep(INTERVAL)
                continue
            newest_message = messages[0]
            if last_message_id is None:
                last_message_id = newest_message.id
                save_last_id(last_message_id)
                await asyncio.sleep(INTERVAL)
                continue
            if newest_message.id != last_message_id:
                no_new_messages_count = 0
                all_lines.clear()
                for msg in messages:
                    if msg.id == last_message_id:
                        break
                    content = msg.clean_content.strip()
                    lines = [l.strip() for l in content.splitlines() if l.strip()]
                    if msg.author.bot:
                        parsed = detect_roll_type_and_parse(lines)
                        all_lines.extend(parsed)
                    else:
                        member = msg.guild.get_member(msg.author.id)
                        if not member:
                            try:
                                member = await msg.guild.fetch_member(msg.author.id)
                            except:
                                member = None
                        display_name = member.display_name if member else msg.author.name
                        if content:
                            all_lines.append(f"{display_name}: {content}")
                formatted_lines = format_columns_all(all_lines)
                with open(FILE_PATH, "w", encoding="utf-8") as f:
                    f.write("\n".join(formatted_lines))
                print("💾 Nalezeny nové zprávy.")
                last_message_id = newest_message.id
                save_last_id(last_message_id)
                empty_written = False
            else:
                no_new_messages_count += 1
                if no_new_messages_count >= 2 and not empty_written:
                    open(FILE_PATH, "w", encoding="utf-8").close()
                    print("⚪ Žádné nové zprávy – soubor vyprázdněn.")
                    empty_written = True
        except Exception as e:
            print("❌ Chyba:", e)
        sleep_time = INTERVAL
        num_lines = len(all_lines)
        if num_lines > 14:
            extra_blocks = (num_lines - 14 + 6) // 7
            sleep_time += extra_blocks * 5
        await asyncio.sleep(sleep_time)

client.run(TOKEN)