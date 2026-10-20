#!/usr/bin/env bash
# Linux equivalent of setup_global_command.ps1 - makes 'albumpaper' runnable from anywhere
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"
ln -sf "$DIR/AlbumPaper.sh" "$BIN_DIR/albumpaper"
echo "Global command 'albumpaper' linked into $BIN_DIR"

case ":$PATH:" in
    *":$BIN_DIR:"*)
        echo "Try typing: albumpaper"
        ;;
    *)
        echo "$BIN_DIR is not on your PATH yet."
        echo "Add this to your ~/.bashrc (or ~/.zshrc) and restart your terminal:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac
