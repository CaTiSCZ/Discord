# image_processor.py
import requests
import os
import logging

logger = logging.getLogger(__name__)

def upload_image(file_path):
    """
    Uploads an image file to the local server and returns the URL.
    """
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'application/octet-stream')}
            response = requests.post('http://localhost:8080/upload', files=files)
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