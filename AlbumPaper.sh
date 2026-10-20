#!/usr/bin/env bash
# Linux launcher, equivalent of AlbumPaper.bat
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/albumpaper"
exec "$DIR/.venv/bin/python" albumpaper.py
