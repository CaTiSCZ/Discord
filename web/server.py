# web/server.py
#import asyncio
import socketio
from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import Response
import uvicorn
import logging
import sys
import os
import mimetypes
import base64
from dispatcher import dispatcher
import urllib.parse

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

# In-memory storage for uploaded images
uploaded_images = {}

# Nastavení šablon a statických souborů
templates = Jinja2Templates(directory="web/templates")

# --- Trasy (Routes) ---

@app.get("/")
async def overlay(request: Request):
    """Zobrazí hlavní display pro OBS."""
    return templates.TemplateResponse("display.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload souboru a vrať URL."""
    upload_dir = "web/static/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    url = f"http://127.0.0.1:8080/static/uploads/{file.filename}"
    logger.debug(f"File uploaded: {file_path}, URL: {url}")
    return {"url": url}

@app.post("/upload_b64")
async def upload_b64(data: dict):
    """Upload base64 image and return URL."""
    img_b64 = data['image']
    filename = data['filename']
    uploaded_images[filename] = base64.b64decode(img_b64)
    logger.debug(f"Stored image: {filename}, size: {len(uploaded_images[filename])}")
    url = f"http://127.0.0.1:8080/static/uploads/{urllib.parse.quote(filename)}"
    logger.debug(f"Base64 image uploaded to memory: {filename}, URL: {url}")
    return {"url": url}

@app.get("/static/uploads/{filename}")
async def get_uploaded_image(filename: str):
    """Serve uploaded image from memory."""
    logger.debug(f"Requesting image: {filename}")
    logger.debug(f"Available images: {list(uploaded_images.keys())}")
    if filename in uploaded_images:
        media_type = mimetypes.guess_type(filename)[0] or "image/png"
        logger.debug(f"Serving image: {filename}, type: {media_type}")
        return Response(content=uploaded_images[filename], media_type=media_type)
    else:
        logger.debug(f"Image not found: {filename}")
        return Response(status_code=404, content="Image not found")

@app.delete("/static/uploads/{filename}")
async def delete_uploaded_image(filename: str):
    """Delete uploaded image from memory."""
    logger.debug(f"Deleting image: {filename}")
    if filename in uploaded_images:
        del uploaded_images[filename]
        logger.debug(f"Image deleted from memory: {filename}")
        return Response(status_code=204)
    else:
        logger.debug(f"Image not found for deletion: {filename}")
        return Response(status_code=404, content="Image not found")

# Mount static files after routes to allow routes to take precedence
app.mount("/static", StaticFiles(directory="web/static"), name="static")

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
    await dispatcher.update_connection_status(True)

@sio.event
async def disconnect(sid):
    logger.info(f"Connection closed")
    logger.debug(f"Disconnected: {sid}")
    await dispatcher.update_connection_status(False)

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
        host="127.0.0.1", 
        port=port, 
        log_level="info",
        access_log=False,
    )
    server_instance = uvicorn.Server(config)
    try:
        logger.info(f"Web server starting: http://127.0.0.1:{port}")
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