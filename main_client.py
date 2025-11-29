#main_client.py
import discord
import asyncio
import json
import os
from channel_watcher import ChannelWatcher
from keyboard_listener import KeyboardListener

CONFIG_FILE = "config.json"


# -------------------------------------------------------------
def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"{CONFIG_FILE} not found. Run config_gui.py first.")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------------
async def start_watchers(client, config, listener):
    watchers = []
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
        )
        watchers.append(watcher)
        listener.register_callback(watcher.on_keypress)

    print(f"📡 Starting {len(watchers)} watchers...")

    await asyncio.gather(*(w.run() for w in watchers))


# -------------------------------------------------------------
def main():
    config = load_config()

    TOKEN = config.get("TOKEN", "").strip()
    if not TOKEN:
        raise RuntimeError("TOKEN not defined in config.json (use config_gui.py to set it).")

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    # Create new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Keyboard listener thread
    listener = KeyboardListener(loop)
    listener.start()

    @client.event
    async def on_ready():
        print(f"✅ Logged in as {client.user}")
        asyncio.create_task(start_watchers(client, config, listener))

    try:
        loop.run_until_complete(client.start(TOKEN))

    except KeyboardInterrupt:
        print("❌ Interrupted via Ctrl+C")

    except RuntimeError as e:
        if "Event loop stopped" not in str(e):
            raise

    finally:
        print("🛑 Shutting down Discord client...")
        loop.run_until_complete(client.close())

        print("🛑 Stopping keyboard listener...")
        listener.stop()

        # Cancel all remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass

        loop.close()
        print("🏁 Shutdown complete.")


# -------------------------------------------------------------
if __name__ == "__main__":
    main()
