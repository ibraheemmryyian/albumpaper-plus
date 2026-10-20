#!/usr/bin/env bash
# Linux equivalent of add_to_startup.ps1 - registers AlbumPaper-Plus to start on login
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/albumpaper-plus.desktop"

mkdir -p "$AUTOSTART_DIR"
cat > "$DESKTOP_FILE" <<EOT
[Desktop Entry]
Type=Application
Name=AlbumPaper-Plus
Comment=Change desktop wallpaper based on the track you're listening to
Exec=$DIR/AlbumPaper-Plus.sh
Icon=$DIR/albumpaper/assets/icons/enabled.png
Terminal=false
X-GNOME-Autostart-enabled=true
EOT

chmod +x "$DESKTOP_FILE"
echo "Autostart entry created at: $DESKTOP_FILE"
echo "AlbumPaper-Plus will now start automatically when you log in!"
