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
from web.server import app, sio, start_web_server, stop_web_server
from logger import setup_logger

logger = setup_logger("MainClient", level=logging.DEBUG)

CONFIG_FILE = "config.json"


# -------------------------------------------------------------
def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} not found. Run config_gui.py first.")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------------------------------------------
async def start_watchers(client, config, loop, keyboard_listener: KeyboardListener = None):
    watchers = []
    tasks = []
    for w in config["watchers"]:
        comment = w.get("comment", "Bez popisu")
        channel_id = w.get("channel_id", "Neznámé ID")
        if not w.get("enabled", True):
            logger.debug(f"Skipping watcher: [{comment}] (ID: {channel_id})")
            continue
        # Create a ChannelWatcher instance from config.json data
        logger.info(f"Startuji watcher: [{comment}] pro kanál {channel_id}")
        watcher = ChannelWatcher(
            client=client,
            channel_id=int(w["channel_id"]),
            file_path=w["file_path"],
            last_id_file=w["last_id_file"],
            socket_panel=w.get("socket_panel", "panel-a"),
            interval=int(w["interval"]),
            history_limit=int(w["history_limit"]),
            show_author_mode=w.get("show_author_mode"),
            ignore_mode=w.get("ignore_mode"),
            manual_clear=bool(w["manual_clear"]),
            max_rows_per_column=int(w["max_rows_per_column"]),
            max_column_width=int(w["max_column_width"]),
            column_spacing=int(w.get("column_spacing", 2)),
            txt_output=bool(w["txt_output"]),
            header_text=w.get("header_text", "") or "",
            sio=sio,
            loop=loop,
        )
        # pokud máme KeyboardListener, zaregistruj on_keypress callback
        if keyboard_listener:
            keyboard_listener.register_callback(watcher.on_keypress)
        watchers.append(watcher)
        tasks.append(loop.create_task(watcher.run()))

    logger.debug(f"Starting {len(watchers)} watchers...")
    
    return watchers, tasks


# nová funkce: spustí klienta v předaném loopu a použije keyboard_listener
def run_client_with_loop(config, loop: asyncio.AbstractEventLoop, keyboard_listener: KeyboardListener = None):
    # TODO: zkontrolovat, jestli jsme opravou gui.save_config nerozbili config, který se používá tady
    TOKEN = config.get("TOKEN", "").strip()
    if not TOKEN:
        raise RuntimeError("TOKEN not defined in config.json (use config_gui.py to set it).")

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    active_watchers = []
    active_tasks = []

    asyncio.set_event_loop(loop)

    @client.event
    async def on_ready():
        nonlocal active_watchers, active_tasks
        logger.debug(f"Logged in as {client.user}")
        loop.create_task(start_web_server())
        watchers, tasks = await start_watchers(client, config, loop, keyboard_listener)
        active_watchers.extend(watchers)
        active_tasks.extend(tasks)

    try:
        loop.run_until_complete(client.start(TOKEN))
        logger.info("Client has stopped.")
    except Exception as e:
        logger.error(f"Client run error: {e}")    

    finally:
        logger.info("Shutting down Discord client...")
        stop_web_server()
        # Musíme zkontrolovat, jestli loop ještě běží, než v něm něco spustíme
        if not client.is_closed() or not loop.is_closed():
            try:
                loop.run_until_complete(client.close())
                loop.run_until_complete(asyncio.sleep(0.5))
            

        
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                    logger.error(f"Error during cleanup: {e}")

        logger.info("Cleanup complete, server stopped.")


# -------------------------------------------------------------
# ... (předchozí kód: importy, Formatter, Watcher) ...

def main():
    config = load_config()
    if not config.get("watchers"):
        logger.error("No watchers defined in config.json.")
        return

    # 1. Inicializace KeyboardListeneru (pokud ho chceš používat)
    kb_listener = KeyboardListener()
    kb_listener.start() # Běží ve vlastním vlákně (v pořádku)

    # 2. Vytvoření loopu pro celou aplikaci
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # 3. Spuštění všeho skrze run_client_with_loop
        run_client_with_loop(config, loop, keyboard_listener=kb_listener)
    except Exception as e:
        logger.error(f"Client launch failed: {e}")
    finally:
        # 4. Úklid po vypnutí
        if kb_listener:
            kb_listener.stop() 

if __name__ == "__main__":
    # Pokud existuje config_gui, spustíme ho, jinak hned main
    script_path = os.path.join(os.path.dirname(__file__), "config_gui.py")
    if os.path.exists(script_path):
        try:
            subprocess.run([sys.executable, script_path])
        except Exception as e:
            main()
    else:
        main()
