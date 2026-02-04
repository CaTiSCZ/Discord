# image_processor.py
import requests
import base64
import io
from PIL import Image
import logging
import time
import os
import urllib.parse

logger = logging.getLogger(__name__)

def upload_image_from_pil(img):
    """
    Uploads a PIL image directly without saving to disk.
    """
    # Convert to bytes
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()
    
    # Encode to base64
    img_b64 = base64.b64encode(img_bytes).decode('utf-8')
    
    try:
        response = requests.post('http://127.0.0.1:8080/upload_b64', json={'image': img_b64, 'filename': f'pasted_image_{int(time.time())}.png'})
        if response.status_code == 200:
            url = response.json()['url']
            logger.debug(f"Image uploaded: {url}")
            return url
        else:
            logger.error(f"Upload failed: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        return None

def upload_image(file_path):
    """
    Uploads an image file.
    """
    try:
        with open(file_path, 'rb') as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        filename = os.path.basename(file_path)
        response = requests.post('http://127.0.0.1:8080/upload_b64', json={'image': img_b64, 'filename': filename})
        if response.status_code == 200:
            url = response.json()['url']
            logger.debug(f"Image uploaded: {url}")
            return url
        else:
            logger.error(f"Upload failed: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        return None