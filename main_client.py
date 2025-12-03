#main_client.py
import discord
import asyncio
import json
import os
import sys
import logging
import subprocess
from channel_watcher import ChannelWatcher
from keyboard_listener import KeyboardListener

logger = logging.getLogger("DiscordWatcher.MainClient")

CONFIG_FILE = "config.json"


# -------------------------------------------------------------
def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} not found. Run config_gui.py first.")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------------
async def start_watchers(client, config, keyboard_listener: KeyboardListener = None):
    watchers = []
    tasks = []
    for w in config["watchers"]:
        # Create a ChannelWatcher instance from config.json data
        watcher = ChannelWatcher(
            client=client,
            channel_id=int(w["channel_id"]),
            file_path=w["file_path"],
            last_id_file=w["last_id_file"],
            interval=int(w["interval"]),
            history_limit=int(w["history_limit"]),
            show_author_mode=None if w["show_author_mode"] == "None" else w["show_author_mode"],
            ignore_mode=None if w["ignore_mode"] == "None" else w["ignore_mode"],
            manual_clear=bool(w["manual_clear"]),
            max_rows_per_column=int(w["max_rows_per_column"]),
            max_column_width=int(w["max_column_width"]),
            column_spacing=int(w.get("column_spacing", 2)),
            txt_output=bool(w["txt_output"]),
            iniciativa_mode=bool(w.get("iniciativa_mode", False)),
        )
        # pokud máme KeyboardListener, zaregistruj on_keypress callback
        if keyboard_listener:
            keyboard_listener.register_callback(watcher.on_keypress)
        watchers.append(watcher)
        tasks.append(asyncio.create_task(watcher.run()))

    logger.info(f"Starting {len(watchers)} watchers...")
    await asyncio.gather(*tasks)


# nová funkce: spustí klienta v předaném loopu a použije keyboard_listener
def run_client_with_loop(config, loop: asyncio.AbstractEventLoop, keyboard_listener: KeyboardListener = None):
    TOKEN = config.get("TOKEN", "").strip()
    if not TOKEN:
        raise RuntimeError("TOKEN not defined in config.json (use config_gui.py to set it).")

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    asyncio.set_event_loop(loop)

    @client.event
    async def on_ready():
        logger.info(f"Logged in as {client.user}")
        # spustit watchers v tomtéž loopu, předat keyboard_listener
        asyncio.create_task(start_watchers(client, config, keyboard_listener))

    try:
        loop.run_until_complete(client.start(TOKEN))
        logger.info("Client has stopped.")

    except KeyboardInterrupt:
        logger.info("Interrupt – ukončuji bota a watchery...")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))

    except RuntimeError as e:
        if "Event loop stopped" not in str(e):
            raise

    finally:
        logger.info("Shutting down Discord client...")
        loop.run_until_complete(client.close())
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()
        logger.info("Shutdown complete.")


# -------------------------------------------------------------
def main():
    config = load_config()
    if not config.get("watchers"):
        raise RuntimeError("No watchers defined in config.json (use config_gui.py to set them up).")
    else:
        logger.info(f"Loaded {len(config['watchers'])} watchers from config.json.")

    # Použij run_client_with_loop (vytvoří a spravuje event loop interně)
    loop = asyncio.new_event_loop()
    try:
        run_client_with_loop(config, loop, keyboard_listener=None)
    except Exception as e:
        logger.error(f"Chyba při spuštění klienta: {e}")


# -------------------------------------------------------------
if __name__ == "__main__":
    # Pokud spouštíš main_client.py přímo, otevři GUI (config_gui.py) v samostatném procesu.
    # To zabrání cirkulárním importům (config_gui importuje main_client).
    script_path = os.path.join(os.path.dirname(__file__), "config_gui.py")
    try:
        subprocess.run([sys.executable, script_path])
    except Exception as e:
        logger.error(f"Chyba při spouštění GUI: {e} — fallback na headless main()")
        main()
