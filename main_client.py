import discord
import asyncio
from channel_watcher import ChannelWatcher
from dotenv import load_dotenv
import os

load_dotenv("personal_data.env")

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Přihlášen jako {client.user}")

    watchers = [
        ChannelWatcher(
            client, int(os.getenv("HODY_KOSTKOU")),
            "rolls.html", "rolls_last.txt",
            ignore_bots=False, show_author=True, format_mode="dice"
        ),
        ChannelWatcher(
            client, int(os.getenv("INICIATIVA")),
            "iniciativa.html", "iniciativa_last.txt",
            ignore_bots=True, show_author=False, manual_clear=True
        )
    ]

    for w in watchers:
        await w.start()

client.run(TOKEN)
