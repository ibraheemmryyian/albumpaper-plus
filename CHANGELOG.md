# Changelog

This file records the modifications made to upstream AlbumPaper, as required by GPL-3.0 section 5(a).

Base: [jac0b-w/AlbumPaper](https://github.com/jac0b-w/AlbumPaper) v4.1.0.
Fork work: June to October 2026, by ibraheemmryyian.

## 1.0.0 - 2026-10-20

First release of AlbumPaper-Plus.

### Added
- Weekly default wallpaper from album art chosen out of the user's Spotify top tracks (`albumpaper/top_played.py`), with a `default_wallpaper` settings section. Adds the `user-top-read` OAuth scope.
- GNOME (Linux) desktop integration: wallpaper, lock screen, light/dark mode and accent colour sync (`albumpaper/linux_desktop.py`).
- Pure-Python fallback for the Rust render module, with opensimplex colored noise (`albumpaper/albumpaper_rs.py`).
- Vibrancy-weighted palette selection in `albumpaper/wallpaper.py`.
- Album art download cache in `albumpaper/misc.py`.
- Spotify HTTP 429 handling with `Retry-After` in `albumpaper/spotifyauth.py`.
- Request throttling and an exception handler in `albumpaper/albumpaper.py`.
- Tests for weekly album selection (`albumpaper/test_top_played.py`).
- Linux launcher and startup/global-command scripts.

### Changed
- Named mutex and battery-saver helpers rewritten in `albumpaper/winapi.py`.
- The token cache hash includes the OAuth scope, so existing tokens are refreshed when scopes change.
- Renamed to AlbumPaper-Plus: launchers, startup entries, global command, tray tooltip, single-instance mutex, HTTP user agent, update-check repository.
- Version set to 1.0.0 for this fork.

### Removed
- Mini player window and its Spotify lyrics fetcher (never shown in the fork's UI).
- The `sp_dc` cookie field in Settings.
- Upstream sponsor file (`.github/FUNDING.yml`).
