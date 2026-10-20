"""
Pure Python fallback for the Rust albumpaper_rs module.
Provides the same functionality using PIL/Pillow.
"""

from PIL import Image, ImageDraw, ImageFilter
import random
import math
import os
import sys
import logging

log = logging.getLogger("app")

# Get the app directory for writable files
def get_app_dir():
    """Get the directory where writable files should be stored"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

_app_dir = get_app_dir()
GENERATED_WALLPAPER_PATH = os.path.join(_app_dir, "images/generated_wallpaper.png")


def generate_save_wallpaper(required_args, optional_args):
    """
    Generate and save a wallpaper based on the background type.
    """
    bg_type = required_args.background_type
    foreground = required_args.foreground
    display_size = required_args.display_geometry  # (width, height)
    available_geom = required_args.available_geometry  # (w, h, left, top)
    
    blur_radius = optional_args.blur_radius
    color1 = optional_args.color1
    color2 = optional_args.color2
    
    width, height = display_size
    
    # Generate background based on type
    if bg_type == "SolidColor":
        background = Image.new("RGB", (width, height), color1)
    elif bg_type == "LinearGradient":
        background = create_linear_gradient(width, height, color1, color2)
    elif bg_type == "RadialGradient":
        background = create_radial_gradient(width, height, color1, color2)
    elif bg_type == "ColoredNoise":
        background = create_colored_noise(width, height, color1, color2)
        if blur_radius:
            background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    elif bg_type == "Artwork":
        # Use artwork as background
        artwork = Image.frombytes("RGB", foreground.artwork_size, foreground.artwork_buffer)
        background = artwork.resize((width, height), Image.Resampling.LANCZOS)
        if blur_radius:
            background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    elif bg_type == "DefaultWallpaper":
        # Load default wallpaper
        default_path = "images/default_wallpaper.jpg"
        if os.path.exists(default_path):
            background = Image.open(default_path).convert("RGB")
            background = background.resize((width, height), Image.Resampling.LANCZOS)
        else:
            background = Image.new("RGB", (width, height), (30, 30, 30))
        if blur_radius:
            background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    else:
        background = Image.new("RGB", (width, height), (30, 30, 30))
    
    # Add foreground artwork if enabled
    if foreground.visable:
        artwork = Image.frombytes("RGB", foreground.artwork_size, foreground.artwork_buffer)
        fg_size = foreground.artwork_resize
        
        # Resize artwork maintaining aspect ratio
        artwork.thumbnail((fg_size, fg_size), Image.Resampling.LANCZOS)
        
        # Center the artwork on the available area
        avail_w, avail_h, avail_left, avail_top = available_geom
        center_x = avail_left + (avail_w - artwork.width) // 2
        center_y = avail_top + (avail_h - artwork.height) // 2
        
        background.paste(artwork, (center_x, center_y))
    
    # Save the wallpaper
    try:
        os.makedirs("images", exist_ok=True)
        log.debug(f"Saving wallpaper to {GENERATED_WALLPAPER_PATH}")
        background.save(GENERATED_WALLPAPER_PATH, "PNG")
        log.info("Wallpaper successfully saved")
    except Exception as e:
        log.error(f"Failed to save wallpaper: {e}")
        # Try fall back to CWD if app dir fails
        try:
            cwd_path = "images/generated_wallpaper_fallback.png"
            log.warning(f"Attempting fallback save to {cwd_path}")
            background.save(cwd_path, "PNG")
        except:
            pass
        raise e


def create_linear_gradient(width, height, color1, color2):
    """Create a vertical linear gradient from color1 to color2."""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    
    for y in range(height):
        ratio = y / height
        r = int(color1[0] + (color2[0] - color1[0]) * ratio)
        g = int(color1[1] + (color2[1] - color1[1]) * ratio)
        b = int(color1[2] + (color2[2] - color1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return image


def create_radial_gradient(width, height, color1, color2):
    """Create a radial gradient from center (color1) to edges (color2)."""
    image = Image.new("RGB", (width, height))
    
    center_x, center_y = width // 2, height // 2
    max_dist = math.sqrt(center_x**2 + center_y**2)
    
    for y in range(height):
        for x in range(width):
            dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            ratio = min(dist / max_dist, 1.0)
            r = int(color1[0] + (color2[0] - color1[0]) * ratio)
            g = int(color1[1] + (color2[1] - color1[1]) * ratio)
            b = int(color1[2] + (color2[2] - color1[2]) * ratio)
            image.putpixel((x, y), (r, g, b))
    
    return image


def create_colored_noise(width, height, color1, color2):
    """
    Create a colored noise pattern blending two colors using OpenSimplex noise.
    Colors are interpolated smoothly along the noise field (no hard banding).
    Optimized for performance with reduced resolution noise generation.
    """
    import numpy as np
    
    # Use consistent seed based on colors for reproducibility
    seed = (color1[0] * 256 + color1[1]) * 256 + color1[2]
    
    # Generate at 1/2 resolution for performance (still looks good)
    scale_factor = 2
    small_w = width // scale_factor
    small_h = height // scale_factor
    
    # Scale factor for noise (matches Rust: 7.5 / min dimension at target resolution)
    noise_scale = 7.5 / min(width, height) * scale_factor
    
    try:
        from opensimplex import OpenSimplex
        gen = OpenSimplex(seed=seed)
        
        noise_array = np.zeros((small_h, small_w), dtype=np.float32)
        
        for y in range(small_h):
            y_scaled = y * noise_scale
            for x in range(small_w):
                noise_array[y, x] = gen.noise2(x * noise_scale, y_scaled)
                
    except ImportError:
        # Fallback: smooth random noise
        np.random.seed(seed % (2**31))
        
        small_scale = max(min(small_w, small_h) // 16, 8)
        base = np.random.rand(small_h // small_scale + 2, small_w // small_scale + 2).astype(np.float32)
        
        from PIL import Image as PILImage
        noise_img = PILImage.fromarray((base * 255).astype(np.uint8), mode='L')
        noise_img = noise_img.resize((small_w, small_h), PILImage.Resampling.BICUBIC)
        noise_array = (np.array(noise_img, dtype=np.float32) / 255.0) * 2 - 1
    
    # Upscale noise to full resolution
    from PIL import Image as PILImage
    noise_0_1 = (noise_array + 0.5)  # Map from [-0.5, 0.5] to [0, 1]
    noise_0_1 = np.clip(noise_0_1, 0, 1)
    noise_img = PILImage.fromarray((noise_0_1 * 255).astype(np.uint8), mode='L')
    noise_img = noise_img.resize((width, height), PILImage.Resampling.BILINEAR)
    t = np.array(noise_img, dtype=np.float32) / 255.0

    # Smooth linear interpolation between color1 and color2 along the noise field
    r1, g1, b1 = color1
    r2, g2, b2 = color2

    r = (r1 + (r2 - r1) * t).astype(np.uint8)
    g = (g1 + (g2 - g1) * t).astype(np.uint8)
    b = (b1 + (b2 - b1) * t).astype(np.uint8)

    rgb = np.stack([r, g, b], axis=2)

    return Image.fromarray(rgb, mode='RGB')
