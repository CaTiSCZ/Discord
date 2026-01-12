import asyncio
from event import on_panel_update

async def watcher_test_loop():
    i = 0
    while True:
        await asyncio.sleep(5)
        i += 1
        on_panel_update.emit(panel="panel-b", text=f"TestWatcher {i}")
