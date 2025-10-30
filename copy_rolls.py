import discord
import asyncio
import os
import re
import textwrap
from dotenv import load_dotenv

load_dotenv("personal_data.env")

FILE_PATH = os.getenv("FILE_PATH", "rolls.txt")
LAST_ID_FILE = os.getenv("LAST_ID_FILE", "log_file.txt" )
INTERVAL = 10
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
max_rows_per_column: int = 9
max_column_width: int = 40
column_spacing: int = 2

def load_last_id():
    if os.path.exists(LAST_ID_FILE):
        try:
            content = open(LAST_ID_FILE, "r").read().strip()
            return int(content) if content else None
        except ValueError:
            return None
    return None

def save_last_id(msg_id: int):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(msg_id))

def format_columns_all(content_lines, max_rows=max_rows_per_column, max_width=max_column_width, spacing=column_spacing):
    #Zalomí dlouhé řádky, rozdělí řádky do sloupců pro lepší čitelnost, 9 řádků na sloupec, 40 znaků šířka sloupce, 2 mezery mezi sloupci
    #sloupce se vyrovnají podle nejdelšího řádku v daném sloupci
    wrapped_lines = []
    for line in content_lines:
        wrapped_lines.extend(textwrap.wrap(line, width=max_width, break_long_words=False) or [""])
    n = len(wrapped_lines)
    if n <= max_rows:
        return wrapped_lines
    num_cols = (n + max_rows - 1) // max_rows
    cols = []
    for c in range(num_cols):
        start = c * max_rows
        end = min(start + max_rows, n)
        cols.append(wrapped_lines[start:end])
    col_widths = [min(max(len(line) for line in col), max_width) for col in cols]
    max_len = max(len(col) for col in cols)
    for col in cols:
        while len(col) < max_len:
            col.append("")
    output_lines = []
    for i in range(max_len):
        row = ""
        for col, width in zip(cols, col_widths):
            row += col[i].ljust(width + spacing)
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
    player_line, roll_line, total_value = lines
    player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"
    return [f"{player_name} - {roll_line.strip()} = {total_value.strip()}"]

def parse_multi_roll(lines):
    player_line = lines[0]
    player_name = player_line.split()[0][1:] if player_line.startswith("@") else "Unknown"

    rolling_line_idx = next((i for i, l in enumerate(lines) if "Rolling" in l), 1)
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

    # zpracování jednotlivých hodů
    raw_rolls = []
    for line in lines[rolling_line_idx+1:-1]:
        if line.strip():
            raw_rolls.append(line)

    # najít max délku části před + nebo =
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
        max_len = max(max_len, len(pre))

    # doplnit mezery a přidat číslování
    roll_lines = []
    for idx, (pre, post) in enumerate(split_rolls, 1):
        pre_padded = pre.ljust(max_len)
        roll_lines.append(f"{idx}. {pre_padded} {post}".rstrip())

    return [header] + roll_lines + [lines[-1]]


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
    text = text.replace("__", "").replace("`", "")
    text = text.replace("kh1", "(adv)").replace("kl1", "(dis)")
    for prefix in ("**result**:", "**total**:"):
        if text.lower().startswith(prefix):
            text = text.split(":", 1)[1].strip()
            break
    # převod markdown na HTML
    text = re.sub(r"~~(.*?)~~", r"<s>\1</s>", text)  # přeškrtnutí
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)  # tučné
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)  # kurzíva  
    
    return text
def save_html(all_lines: list[str], file_path: str):
    # všechny řádky už jsou normalized a obsahují HTML tagy (<b>, <i>, <s>)
    html_lines = "\n".join(all_lines)
    html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta charset="UTF-8">
<meta http-equiv="refresh" content="1">
<meta charset="UTF-8">
<title>Rolls</title>
<style>
body {{
    background-color: #000000;   /* černé pozadí */
    color: #ffffff;              /* bílé písmo */
    font-family: monospace;      /* monospace font pro zarovnání */
    margin: 0px;
    padding: 0px;
    overflow: hidden;
    white-space: pre;            /* zachování odsazení a sloupců */
    font-size: 24px;
    line-height: 1.2;
}}
b {{ font-weight: bold; }}
i {{ font-style: italic; }}
s {{ text-decoration: line-through; }}
</style>
</head>
<body>
<pre>
{html_lines}
</pre>
</body>
</html>
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)



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

async def fetch_messages(channel: discord.TextChannel, after_id: int | None = None) -> list[discord.Message]:
    """Načte všechny nové zprávy od last_message_id, seřazené od starší po novější."""
    if after_id:
        messages = [msg async for msg in channel.history(limit=None, after=discord.Object(id=after_id))]
    else:
        messages = [msg async for msg in channel.history(limit=HISTORY_LIMIT)]
    messages.sort(key=lambda m: m.created_at)  # starší nahoře
    return messages

async def process_messages(messages: list[discord.Message]) -> list[str]:
    all_lines: list[str] = []
    for msg in messages:
        content = msg.clean_content.strip()
        lines = [normalize_roll_line(l.strip()) for l in content.splitlines() if l.strip()]
        if msg.author.bot:
            parsed = detect_roll_type_and_parse(lines)
            all_lines.extend(parsed)
        else:
            member = msg.guild.get_member(msg.author.id) or await msg.guild.fetch_member(msg.author.id)
            display_name = getattr(member, "display_name", msg.author.name)
            if content:
                normalized = normalize_roll_line(content)
                all_lines.append(f"{display_name}: {normalized}")

    return all_lines

async def monitor_channel(channel: discord.TextChannel):
    global last_message_id, empty_written, no_new_messages_count
    while True:
        try:
            messages = await fetch_messages(channel, last_message_id)
            if not messages:
                no_new_messages_count += 1
                if no_new_messages_count >= 2 and not empty_written:
                    open(FILE_PATH, "w", encoding="utf-8").close()
                    print("Žádné nové zprávy – soubor vyprázdněn.")
                    empty_written = True
                await asyncio.sleep(INTERVAL)
                continue

            all_lines = await process_messages(messages)
            if all_lines:
                formatted = format_columns_all(all_lines)
                save_html(formatted, FILE_PATH)
                print("Nalezeny nové zprávy.")
            last_message_id = messages[-1].id
            save_last_id(last_message_id)
            empty_written = False
            no_new_messages_count = 0

        except Exception as e:
            print("Chyba monitor_channel:", e)

        # dynamické prodloužení spánku podle počtu řádků
        sleep_time = INTERVAL
        if len(all_lines) > max_rows_per_column:
            extend_time = 5
            max_column = 5
            sleep_time += min((max(len(all_lines) - max_rows_per_column, 0) + max_rows_per_column-1) // max_rows_per_column, max_column) * extend_time
        await asyncio.sleep(sleep_time)


client.run(TOKEN)