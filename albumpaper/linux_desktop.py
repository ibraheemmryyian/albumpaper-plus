"""
GNOME desktop integration used on Linux: setting the wallpaper/lock-screen
background and syncing the system light/dark mode + accent color to the
generated wallpaper's dominant color.

Implemented via the `gsettings` CLI rather than PyGObject bindings so it
works in any venv without needing python3-gi installed system-wide, and
works the same way under both X11 and Wayland.
"""

import colorsys
import logging
import subprocess
from typing import Optional
from urllib.parse import urlparse, unquote, quote

log = logging.getLogger("app")

BACKGROUND_SCHEMA = "org.gnome.desktop.background"
SCREENSAVER_SCHEMA = "org.gnome.desktop.screensaver"
INTERFACE_SCHEMA = "org.gnome.desktop.interface"

# Approximate RGB swatches for GNOME's fixed accent-color palette
# (org.gnome.desktop.interface accent-color enum)
ACCENT_COLORS = {
    "blue": (53, 132, 228),
    "teal": (33, 144, 164),
    "green": (58, 148, 74),
    "yellow": (200, 142, 6),
    "orange": (230, 97, 0),
    "red": (224, 27, 36),
    "pink": (214, 91, 161),
    "purple": (145, 65, 172),
    "slate": (111, 131, 150),
    "brown": (134, 94, 60),
}


def _gsettings(args: list[str]) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            ["gsettings", *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        log.error(f"gsettings {' '.join(args)} failed: {e}")
        return None


def _file_uri(path: str) -> str:
    return "file://" + quote(path)


def _uri_to_path(uri: str) -> Optional[str]:
    uri = uri.strip().strip("'")
    if not uri:
        return None
    return unquote(urlparse(uri).path)


def set_wallpaper(path: str, update_lockscreen: bool = True) -> None:
    """Set the GNOME desktop background (light + dark slot) and optionally the lock screen."""
    uri = _file_uri(path)
    _gsettings(["set", BACKGROUND_SCHEMA, "picture-uri", uri])
    _gsettings(["set", BACKGROUND_SCHEMA, "picture-uri-dark", uri])
    if update_lockscreen:
        _gsettings(["set", SCREENSAVER_SCHEMA, "picture-uri", uri])


def get_current_wallpaper() -> Optional[str]:
    """Read the current GNOME desktop background path, if any."""
    result = _gsettings(["get", BACKGROUND_SCHEMA, "picture-uri"])
    if result is None:
        return None
    return _uri_to_path(result.stdout)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(rgb: tuple[int, int, int]) -> bool:
    return relative_luminance(rgb) < 0.5


_ACCENT_HUES = {
    name: colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0]
    for name, rgb in ACCENT_COLORS.items()
}


def nearest_accent(rgb: tuple[int, int, int]) -> str:
    """
    Match by hue (not raw RGB distance) so dark/desaturated colors still map to
    the accent with the closest "color identity" rather than the closest
    brightness - e.g. a dark navy should map to blue, not a muddier green.
    Falls back to RGB distance for near-greyscale colors where hue is meaningless.
    """
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if s < 0.1:
        return min(
            ACCENT_COLORS,
            key=lambda name: sum((a - b) ** 2 for a, b in zip(rgb, ACCENT_COLORS[name])),
        )

    def hue_distance(other_h: float) -> float:
        d = abs(h - other_h)
        return min(d, 1 - d)

    return min(_ACCENT_HUES, key=lambda name: hue_distance(_ACCENT_HUES[name]))


def set_color_scheme(dark: bool) -> None:
    _gsettings(
        ["set", INTERFACE_SCHEMA, "color-scheme", "prefer-dark" if dark else "default"]
    )


def set_accent_color(rgb: tuple[int, int, int]) -> str:
    accent = nearest_accent(rgb)
    _gsettings(["set", INTERFACE_SCHEMA, "accent-color", accent])
    return accent


def sync_system_theme(rgb: tuple[int, int, int]) -> None:
    """Switch GNOME light/dark mode and accent color to match an album art color."""
    set_color_scheme(is_dark(rgb))
    set_accent_color(rgb)
