"""
Weekly auto-refresh of the default (idle) wallpaper using the user's
most-played albums on Spotify, so the idle wallpaper isn't stuck on
whatever was manually set once.
"""
import os
import random
import shutil
import time
import logging
from io import BytesIO
from PIL import Image

import misc
from config import ConfigManager
from wallpaper import GenerateWallpaper, GENERATED_WALLPAPER_PATH, DEFAULT_WALLPAPER_PATH

log = logging.getLogger("app")

REFRESH_INTERVAL_SECONDS = 7 * 24 * 60 * 60  # 1 week
TOP_TRACKS_LIMIT = 20
TIME_RANGE = "medium_term"  # Spotify's own rolling ~6 month listening history


def pick_weighted_album(items: list):
    """
    Input: spotify current_user_top_tracks()["items"], ranked most -> least played
    Output: (album_id, art_url) chosen at random, weighted toward higher-ranked
    (more played) albums. Albums are deduplicated so a single album with many
    top tracks doesn't crowd out variety, and picking is randomized (not just
    "always #1") so the wallpaper doesn't repeat every week.
    Returns None if no usable album art was found.
    """
    seen = {}
    for rank, track in enumerate(items):
        album = (track or {}).get("album") or {}
        album_id = album.get("id")
        images = album.get("images") or []
        if not album_id or not images:
            continue
        if album_id not in seen:
            seen[album_id] = {"rank": rank, "url": images[0]["url"]}

    if not seen:
        return None

    album_ids = list(seen.keys())
    weights = [1.0 / (seen[aid]["rank"] + 1) for aid in album_ids]
    chosen_id = random.choices(album_ids, weights=weights, k=1)[0]
    return chosen_id, seen[chosen_id]["url"]


def should_refresh(settings=None) -> bool:
    settings = ConfigManager.settings if settings is None else settings
    section = settings["default_wallpaper"]
    if not section["auto_refresh_enabled"]:
        return False
    return (time.time() - float(section["last_refresh"])) >= REFRESH_INTERVAL_SECONDS


def refresh_default_wallpaper(spotify_api, wallpaper_generator: GenerateWallpaper) -> bool:
    """
    Fetch the user's top tracks, pick one album (weighted toward most-played),
    render it through the current background settings, and save the result as
    the default (idle) wallpaper. Does NOT touch the live/current wallpaper -
    callers decide whether to apply it immediately.
    Returns True on success.
    """
    top_tracks = spotify_api.current_user_top_tracks(
        limit=TOP_TRACKS_LIMIT, time_range=TIME_RANGE
    )
    picked = pick_weighted_album(top_tracks.get("items", []))
    if picked is None:
        log.warning("Top-played wallpaper refresh: no albums found in top tracks")
        return False
    _album_id, art_url = picked

    content = misc.download_image(art_url)
    art = Image.open(BytesIO(content)).convert("RGB")

    # gen_background() unconditionally overwrites GENERATED_WALLPAPER_PATH,
    # which normally holds the render for whatever track is *currently
    # playing*. Snapshot it first and restore it after, so this weekly
    # top-played job can't leave the "now playing" wallpaper file pointing
    # at the wrong album (which would surface later via the
    # previously_generated_url fast-path in albumpaper.py re-applying it).
    previous_generated = None
    if os.path.exists(GENERATED_WALLPAPER_PATH):
        with open(GENERATED_WALLPAPER_PATH, "rb") as f:
            previous_generated = f.read()

    try:
        # gen_background() (not generate()) so this doesn't force-apply the
        # generated image as the *current* wallpaper if a track is playing.
        wallpaper_generator.gen_background(art)
        shutil.copyfile(GENERATED_WALLPAPER_PATH, DEFAULT_WALLPAPER_PATH)
    finally:
        if previous_generated is not None:
            with open(GENERATED_WALLPAPER_PATH, "wb") as f:
                f.write(previous_generated)

    log.info("Default wallpaper refreshed from top-played albums")
    return True
