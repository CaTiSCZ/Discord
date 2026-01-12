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
    print("WS connected")

    try:
        i = 0
        while True:
            await asyncio.sleep(10)
            i += 1
            await ws.send_json({
                "panel": "panel-a",
                "text": f"TEST: zpráva z Python serveru\nČas běží...\nKolo č.: {i}"
            })

    except WebSocketDisconnect:
        print("WS disconnected")

    finally:
        clients.discard(ws)  # bezpečné, nikdy nehodí chybu
