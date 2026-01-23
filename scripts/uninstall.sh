#!/bin/bash
# Uninstaller for Virtual Mic Soundboard

INSTALL_DIR="$HOME/.local/share/virtual-mic-soundboard"
CONFIG_DIR="$HOME/.config/virtual-mic-soundboard"
DESKTOP_ENTRY_NAME="virtual-mic-soundboard.desktop"
DESKTOP_FILE="$HOME/.local/share/applications/$DESKTOP_ENTRY_NAME"

echo "Uninstalling Virtual Mic Soundboard..."

# Remove known desktop entries (including old ones)
echo "Removing desktop entries..."
rm -f "$HOME/.local/share/applications/soundboard.desktop"
rm -f "$HOME/.local/share/applications/VirtualMicSoundboard.desktop"
rm -f "$HOME/.local/share/applications/virtual-mic-soundboard-appimage.desktop"
rm -f "$DESKTOP_FILE"

# Remove icon
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/virtual-mic-soundboard.png"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# Ask about removing configuration
if [ -d "$CONFIG_DIR" ]; then
    read -p "Remove configuration and settings? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "Removed configuration directory"
    fi
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
