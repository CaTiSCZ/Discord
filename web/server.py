from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from starlette.requests import Request
import asyncio

app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

clients: set[WebSocket] = set()

@app.get("/", response_class=HTMLResponse)
async def overlay(request: Request):
    return templates.TemplateResponse("display.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)

    # testovací data po připojení
    await ws.send_json({
        "panel": "panel-a",
        "text": "WebSocket připojen ✔\nČekám na data…"
    })

    try:
        while True:
            # zatím jen udržujeme spojení
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        clients.remove(ws)

# helper – později tohle zavolá watcher
async def broadcast(panel: str, text: str):
    for ws in list(clients):
        await ws.send_json({"panel": panel, "text": text})
