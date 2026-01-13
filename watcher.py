import asyncio
from event import on_panel_update


async def watcher_test_loop():
    i = 0
    try:
        while True:
            await asyncio.sleep(5)
            i += 1
            on_panel_update.emit(panel="panel-b", text=f"TestWatcher {i}")

    except asyncio.CancelledError:
        print("Watcher stopped cleanly")


async def main():
    print("Watcher started")
    await watcher_test_loop()


if __name__ == "__main__":
    asyncio.run(main())
