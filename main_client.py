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

async def start_watchers():
    watchers = [
        ChannelWatcher(
            client, int(os.getenv("TESTOVACI_CH")),
            os.getenv("HODY_KOSTKOU_FILE", "rolls.html"), os.getenv("HODY_LAST_ID", "hody_log.txt" ),
             ignore_mode = None, show_author_mode = "human", manual_clear=False
        ),
        ChannelWatcher(
            client, int(os.getenv("TESTOVACI_CH")),
            os.getenv("INICIATIVA_FILE", "iniciativa_msg.html"), os.getenv("INICIATIVA_LAST_ID", "iniciativa_log.txt"),
            ignore_mode = "bot", show_author_mode=False, manual_clear=True
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
loop = asyncio.get_event_loop()
asyncio.set_event_loop(loop)

# Spuštění keyboard listeneru ve vlastním vlákně
listener = KeyboardListener(loop)
listener.start()

try:
    loop.run_until_complete(client.start(TOKEN))
except KeyboardInterrupt:
    print("❌ Ukončeno přes Ctrl+C")
finally:
    # korektní uzavření klienta
    loop.run_until_complete(client.close())
    loop.close()
    print("✅ Script ukončen.")
