import discord
import asyncio
import os
import re
import textwrap, html
import sys
import threading, msvcrt  
from dotenv import load_dotenv


load_dotenv("personal_data.env")

FILE_PATH = os.getenv("INICIATIVA_FILE", "iniciativa_msg.txt")
LAST_ID_FILE = os.getenv("INICIATIVA_LAST_ID", "iniciativa_log.txt" )
INTERVAL = 10
HISTORY_LIMIT = 10

try:
    TOKEN = os.environ["TOKEN"]
except KeyError:
    raise ValueError("Chybí TOKEN v personal_data.env")
try:
    CHANNEL_ID = int(os.environ["INICIATIVA"])
except KeyError:
    raise ValueError("Chybí CHANNEL_ID v personal_data.env")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

last_message_id: int | None = None
messages_cache: dict[int, str] = {}
delete_enabled = False
max_rows_per_column: int = 9
max_column_width: int = 15
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

def visible_len(s: str) -> int:
    #vrací čistý text bez HTML tagů
    clean = re.sub(r'<[^>]*>', '', s)
    clean = clean.replace("&nbsp;", " ")
    return len(clean)

def smart_wrap(text, width):
    #zalomení textu podle viditelné délky (ignoruje HTML tagy).
    words = text.split()
    lines = []
    current = ""
    current_len = 0

    for w in words:
        w_len = visible_len(w)
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

def format_columns_all(content_lines, max_rows=max_rows_per_column, max_width=max_column_width, spacing=column_spacing):
    # zalamuje řádky podle viditelné délky (ignoruje HTML tagy)
    wrapped_lines = []
    for line in content_lines:
        wrapped_lines.extend(smart_wrap(line, max_width))
    n = len(wrapped_lines)
    if n <= max_rows:
        return wrapped_lines
    num_cols = (n + max_rows - 1) // max_rows
    cols = []
    for c in range(num_cols):
        start = c * max_rows
        end = min(start + max_rows, n)
        cols.append(wrapped_lines[start:end])
    # šířky sloupců podle viditelné délky
    col_widths = [min(max(visible_len(line) for line in col), max_width) for col in cols]
    max_len = max(len(col) for col in cols)
    for col in cols:
        while len(col) < max_len:
            col.append("")
    output_lines = []
    for i in range(max_len):
        row = ""
        for col, width in zip(cols, col_widths):
            line = col[i]
            pad_len = width - visible_len(line)
            row += line + (" " * (pad_len + spacing))
        output_lines.append(row.rstrip())
    return output_lines
    
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
<title>Rolls</title>
<style>
body {{
    background-color: #000000;   /* černé pozadí */
    color: #ffffff;              /* bílé písmo */
    font-family: monospace;      /* monospace font pro zarovnání */
    padding: 0px;
    margin: 0px;
    overflow: visible;
    white-space: pre;            /* zachování odsazení a sloupců */
    font-size: 31px;
}}
pre {{
    margin: 0;
    padding: 0;
    line-height: 1.2;
    min-width: 0;
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


@client.event
async def on_ready():
    global last_message_id
    print(f"✅ Přihlášen jako {client.user}")
    last_message_id = load_last_id()
    if last_message_id:
        print(f"↩️ Načteno ID {last_message_id}")
    else:
        print("🆕 První běh (bez uloženého ID).")
    channel = client.get_channel(CHANNEL_ID)
    await asyncio.gather(
        monitor_channel(channel),
        keyboard_listener()
    )

@client.event
async def on_message_edit(before, after):
    # aktualizace cache při úpravě zprávy
    if after.author.bot:
        return
    messages_cache[after.id] = after.clean_content.strip()
    print(f"✏️ Upravená zpráva: {after.id}")
    await regenerate_display(after.channel)

async def fetch_messages(channel: discord.TextChannel, after_id: int | None = None) -> list[discord.Message]:
    # načte zprávy po after_id (exkluzivně), nebo posledních HISTORY_LIMIT
    if after_id:
        messages = [msg async for msg in channel.history(limit=None, after=discord.Object(id=after_id))]
    else:
        messages = [msg async for msg in channel.history(limit=HISTORY_LIMIT)]
    messages.sort(key=lambda m: m.created_at)  # starší nahoře
    return messages

async def regenerate_display(channel):
    """Znovu vygeneruje obsah HTML ze všech známých zpráv."""
    all_lines = []
    for msg_id, content in messages_cache.items():
        content = normalize_roll_line(content)
        # Zachováme kontrolu autora pro ověření, že zpráva stále existuje
        await channel.fetch_message(msg_id)
        all_lines.append(content)
    formatted = format_columns_all(all_lines)
    save_html(formatted, FILE_PATH)
    print("💾 HTML aktualizováno")

async def monitor_channel(channel: discord.TextChannel):
    global last_message_id, delete_enabled
    last_snapshot = {}
    last_state = None  # sleduje, co se naposledy stalo ("new" nebo "idle")

    while True:
        try:
            messages = await fetch_messages(channel, last_message_id)
            new_detected = False
            new_cache = {}  # Dočasná cache pro nové zprávy
            
            if messages:
                latest_id = messages[-1].id
                if latest_id > (last_message_id or 0):
                    #print(f"📝 Aktualizace last_message_id: {latest_id}")
                    last_message_id = latest_id
                    save_last_id(last_message_id)
                
                # Zpracování nových zpráv
                for msg in messages:
                    if msg.author.bot:
                        continue
                    # Zpracuj každý řádek zprávy zvlášť
                    lines = [line.strip() for line in msg.clean_content.splitlines()]
                    content = "\n".join(line for line in lines if line)  # Zachová prázdné řádky
                    if content:  # ignoruj zcela prázdné zprávy
                        new_cache[msg.id] = content
                        new_detected = True
                
                # Nahraď starou cache novou
                if new_detected:
                    messages_cache.clear()  # Vymaž starou cache
                    messages_cache.update(new_cache)  # Přidej pouze nové zprávy

            # Vyčištění cache od smazaných zpráv
            cached_ids = list(messages_cache.keys())
            for msg_id in cached_ids:
                try:
                    await channel.fetch_message(msg_id)
                except discord.NotFound:
                    del messages_cache[msg_id]
                    new_detected = True  # vyvolá překreslení

            # Aktualizace HTML při jakékoliv změně
            if new_detected or messages_cache != last_snapshot:
                # Rozděl obsah na řádky a zachovej formátování
                all_lines = []
                for content in messages_cache.values():
                    for line in content.splitlines():
                        if line.strip():  # Přidej jen neprázdné řádky
                            all_lines.append(normalize_roll_line(line))
                
                formatted = format_columns_all(all_lines)
                save_html(formatted, FILE_PATH)
                
                delete_enabled = False
                last_snapshot = messages_cache.copy()
                if last_state != "new":
                    print("🆕 Nové nebo změněné zprávy.")
                    last_state = "new"
            else:
                delete_enabled = True
                if last_state != "idle":
                    print("💤 žádná změna (soubor lze smazat klávesou)")
                    last_state = "idle"

        except Exception as e:
            print("❌ Chyba monitor_channel:", e)

        await asyncio.sleep(INTERVAL)

async def keyboard_listener():
    # asynchronní posluchač kláves pro mazání souboru nebo ukončení
    print("⌨️ Libovolná klávesa = smazat, 'q' = ukončit")

    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()  # načte jeden znak (UNICODE)
            if ch.lower() == 'q':
                print("🔴 Konec skriptu")
                sys.exit(0)
            elif os.path.exists(FILE_PATH):
                os.remove(FILE_PATH)
                print("🗑️ Soubor smazán")
        await asyncio.sleep(0.5)

client.run(TOKEN)