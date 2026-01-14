# web/server.py
import asyncio
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uvicorn
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import setup_logger
logger = setup_logger("WebServer", level=logging.INFO)




# 1. Inicializace Socket.io serveru
# cors_allowed_origins="*" zajistí, že se OBS připojí bez ohledu na doménu
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# 2. Vytvoření FastAPI aplikace
app = FastAPI()

# 3. Propojení FastAPI a Socket.io do jedné ASGI aplikace
combined_app = socketio.ASGIApp(sio, app)

server_instance = None

# Nastavení šablon a statických souborů
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# --- Trasy (Routes) ---

@app.get("/")
async def overlay(request: Request):
    """Zobrazí hlavní display pro OBS."""
    return templates.TemplateResponse("display.html", {"request": request})

# --- Socket.io Události ---

@sio.event
async def connect(sid, environ):
    logger.info(f"OBS připojen: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"OBS odpojen: {sid}")

# --- Spouštěcí funkce ---

async def start_web_server(host="0.0.0.0", port=8080):
    """
    Spustí Uvicorn server neblokujícím způsobem. 
    Díky tomu může běžet ve stejném loopu jako Discord.
    """
    global server_instance
    if server_instance and not server_instance.should_exit:
        logger.info("Web server už je aktivní na pozadí.")
        return
    config = uvicorn.Config(
        app=combined_app, 
        host=host, 
        port=port, 
        log_level="info",
        access_log=False,
    )
    server_instance = uvicorn.Server(config)
    try:
        logger.info(f"Web server starting: http://{host}:{port}")
        await server_instance.serve()
    finally:
        server_instance = None 
    

async def stop_web_server():
    global server_instance
    if server_instance:
        logger.info("Vypínám Web Server...")
        server_instance.should_exit = True
        # Malá pauza, aby uvicorn stihl zareagovat a uvolnit port
        await asyncio.sleep(0.5)
        server_instance = None
        logger.info("Web Server byl úspěšně ukončen.")