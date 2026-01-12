from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from starlette.requests import Request
import asyncio
from contextlib import asynccontextmanager

from event import on_panel_update

clients: set[WebSocket] = set()

async def broadcast(panel: str, text: str):
    # pošle všem websocket klientům
    for ws in list(clients):
        try:
            await ws.send_json({"panel": panel, "text": text})
        except:
            clients.discard(ws)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Server startup – připojuji event listener")

    def handle_panel_update(panel: str, text: str):
        asyncio.create_task(broadcast(panel, text))

    on_panel_update.connect(handle_panel_update)

    yield  # ⬅️ server běží

    print("Server shutdown – odpojuji event listener")
    on_panel_update.disconnect(handle_panel_update)


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

@app.get("/", response_class=HTMLResponse)
async def overlay(request: Request):
    return templates.TemplateResponse("display.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    print("WS connected")

    try:
        # Tato smyčka jen udržuje websocket otevřený
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        print("WS disconnected")
    finally:
        clients.discard(ws)


