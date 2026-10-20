from dataclasses import dataclass
import time, requests, functools, sys
from PIL import Image

def timer(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        return_values = func(*args, **kwargs)
        if time.time() - start > 0.005:
            print(f"function {func.__name__} took {time.time() - start} seconds")
        return return_values

    return wrapper

import hashlib, os
from config import get_app_dir

@timer
@functools.lru_cache(10)
def download_image(url):
    # Create cache directory if it doesn't exist
    cache_dir = os.path.join(get_app_dir(), "images", "cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    
    # Create a unique filename for this URL
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    cache_path = os.path.join(cache_dir, f"{url_hash}.jpg")
    
    # Check if we have it cached
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()
    
    # Otherwise, download and cache it
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.content
        
        # Save to cache
        with open(cache_path, "wb") as f:
            f.write(content)
            
        # Optional: Limit cache size (keep last 100)
        files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir)]
        if len(files) > 100:
            files.sort(key=os.path.getmtime)
            for i in range(len(files) - 100):
                try: os.remove(files[i])
                except: pass
                
        return content
    except Exception as e:
        print(f"Error downloading image: {e}")
        raise e

@dataclass
class HashableImage:
    image: Image.Image
    def __hash__(self):
        return hash(self.image.tobytes("raw"))
