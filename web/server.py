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
logger = setup_logger("WebServer", level=logging.DEBUG)




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
    ip = environ.get('REMOTE_ADDR', 'Unknown IP')
    user_agent = environ.get('HTTP_USER_AGENT', 'Unknown device')
    
    client_name = "Unknown client"
    if "OBS" in user_agent:
        client_name = "OBS Studio"
    elif "Chrome" in user_agent or "Mozilla" in user_agent:
        client_name = "Internet Browser"
    else:
        client_name = user_agent.split("/")[0]  # Zkusíme získat název klienta z User-Agent

    # Teď bude log vypadat mnohem lépe
    logger.info(f"Connection opened: {client_name} ")
    logger.debug(f"Technical SID: {sid}, (IP: {ip}), User-Agent: {user_agent}")

@sio.event
async def disconnect(sid):
    logger.info(f"Connection closed")
    logger.debug(f"Disconnected: {sid}")

# --- Spouštěcí funkce ---

async def start_web_server(host="0.0.0.0", port=8080):
    """
    Spustí Uvicorn server neblokujícím způsobem. 
    Díky tomu může běžet ve stejném loopu jako Discord.
    """
    global server_instance
    if server_instance and not server_instance.should_exit:
        logger.info("Server is already running.")
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
        logger.debug("Shutting down Web Server...")
        server_instance.should_exit = True
        if hasattr(server_instance, 'shutdown'):
            await server_instance.shutdown()
        server_instance = None
        logger.debug("Web Server was successfully shut down.")
    else:
        logger.info("Web Server is not running.")