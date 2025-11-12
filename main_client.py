# main_client.py
import discord
import asyncio
from channel_watcher import ChannelWatcher
from dotenv import load_dotenv
import os
from keyboard_listener import KeyboardListener

load_dotenv("personal_data.env")
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
stop_flag = asyncio.Event()

async def start_watchers():
    watchers = [
        ChannelWatcher(
            client, int(os.getenv("TESTOVACI_CH")),
            os.getenv("HODY_KOSTKOU_FILE", "rolls.html"), os.getenv("HODY_LAST_ID", "hody_log.txt" ),
             ignore_mode = None, show_author_mode = "human", manual_clear=False, listener=listener
        ),
        ChannelWatcher(
            client, int(os.getenv("TESTOVACI_CH")),
            os.getenv("INICIATIVA_FILE", "iniciativa_msg.html"), os.getenv("INICIATIVA_LAST_ID", "iniciativa_log.txt"),
            ignore_mode = "bot", show_author_mode=False, manual_clear=True, listener=listener
        )
    ]
    # spustí všechny watchery současně
    await asyncio.gather(*(w.run() for w in watchers))

@client.event
async def on_ready():
    print(f"✅ Přihlášen jako {client.user}")
    # spustíme watchery
    asyncio.create_task(start_watchers())

# Získání hlavního event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Spuštění keyboard listeneru ve vlastním vlákně
listener = KeyboardListener(loop)
listener.start()

try:
    loop.run_until_complete(client.start(TOKEN))
except KeyboardInterrupt:
    print("❌ Ukončeno přes Ctrl+C")

except RuntimeError as e:
    if str(e) != "Event loop stopped before Future completed.":
        raise
finally:
    # uzavření klienta
    loop.run_until_complete(client.close())

    # ukončení keyboard listeneru
    if hasattr(listener, "stop"):
        listener.stop()

    # zrušení všech zbývajících tasků
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    try:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception as e:
        if not isinstance(e, asyncio.CancelledError):
            print(f"Chyba při rušení tasků: {e}")

    loop.close()
    print("✅ Script ukončen.")