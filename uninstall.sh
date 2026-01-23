#!/bin/bash
# Uninstaller for Virtual Mic Soundboard

INSTALL_DIR="$HOME/.local/share/virtual-mic-soundboard"
DESKTOP_FILE="$HOME/.local/share/applications/soundboard.desktop"

echo "Uninstalling Virtual Mic Soundboard..."

# Remove desktop entry
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "Removed desktop shortcut"
fi

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

# Ask about removing installation directory
if [ -d "$INSTALL_DIR" ]; then
    read -p "Remove installation directory and all data? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        echo "Removed installation directory"
    else
        echo "Kept installation directory: $INSTALL_DIR"
    fi
fi

echo "Uninstallation complete!"
