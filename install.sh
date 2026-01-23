#!/bin/bash
# Universal installer for Virtual Mic Soundboard
# Works on Ubuntu, Fedora, Arch, and other Linux distributions

set -e

REPO_URL="https://github.com/antimassV/virtual-mic-soundboard"
INSTALL_DIR="$HOME/.local/share/virtual-mic-soundboard"
DESKTOP_FILE="$HOME/.local/share/applications/soundboard.desktop"

echo "========================================="
echo "Virtual Mic Soundboard Installer"
echo "========================================="
echo ""
echo "Privacy Notice:"
echo "This app uses pynput to detect global hotkeys."
echo "Keystrokes are NOT recorded or sent anywhere."
echo "They are only used locally to trigger sounds."
echo ""

# Detect package manager
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt"
    INSTALL_CMD="sudo apt-get install -y"
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    INSTALL_CMD="sudo pacman -S --noconfirm"
else
    echo "Warning: Could not detect package manager. You may need to install dependencies manually."
    PKG_MANAGER="unknown"
fi

# Check for required system packages
echo "Checking system dependencies..."

check_and_install() {
    local package=$1
    local apt_name=$2
    local dnf_name=$3
    local pacman_name=$4
    
    if ! command -v $package &> /dev/null; then
        echo "Installing $package..."
        case $PKG_MANAGER in
            apt)
                $INSTALL_CMD $apt_name
                ;;
            dnf)
                $INSTALL_CMD $dnf_name
                ;;
            pacman)
                $INSTALL_CMD $pacman_name
                ;;
            *)
                echo "Please install $package manually"
                ;;
        esac
    fi
}

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed."
    check_and_install python3 python3 python3 python
fi

# Check PipeWire/PulseAudio tools
if ! command -v pactl &> /dev/null; then
    echo "PulseAudio/PipeWire tools not found. Installing..."
    case $PKG_MANAGER in
        apt)
            $INSTALL_CMD pulseaudio-utils pipewire-pulse
            ;;
        dnf)
            $INSTALL_CMD pulseaudio-utils pipewire-pulseaudio
            ;;
        pacman)
            $INSTALL_CMD pipewire-pulse
            ;;
    esac
fi

# Check for audio libraries
case $PKG_MANAGER in
    apt)
        $INSTALL_CMD libportaudio2 libsndfile1 ffmpeg
        ;;
    dnf)
        $INSTALL_CMD portaudio libsndfile ffmpeg
        ;;
    pacman)
        $INSTALL_CMD portaudio libsndfile ffmpeg
        ;;
esac

# Create installation directory
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# If running from git repo, copy files
if [ -d "src" ]; then
    echo "Installing from local directory..."
    cp -r src "$INSTALL_DIR/"
    cp -r assets "$INSTALL_DIR/"
    cp -r scripts "$INSTALL_DIR/"
    # Copy root files
    cp requirements.txt "$INSTALL_DIR/"
    cp run_soundboard.sh "$INSTALL_DIR/"
    # Copy Uninstall script specifically
    cp scripts/uninstall.sh "$INSTALL_DIR/"
else
    # Download from GitHub
    echo "Downloading from GitHub..."
    if command -v git &> /dev/null; then
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        echo "Git not found. Installing..."
        check_and_install git git git git
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
fi

cd "$INSTALL_DIR"

# Create virtual environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Make scripts executable
chmod +x run_soundboard.sh
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x uninstall.sh

# Create desktop entry
echo "Creating desktop shortcut..."
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Virtual Mic Soundboard
Comment=Play sounds through a virtual microphone
Exec="$INSTALL_DIR/run_soundboard.sh"
Icon=$INSTALL_DIR/assets/icon.png
Path=$INSTALL_DIR
Terminal=false
Categories=Audio;AudioVideo;
StartupNotify=false
StartupWMClass=soundboard
X-GNOME-Autostart-enabled=false
EOF

chmod +x "$DESKTOP_FILE"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications"
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t ~/.local/share/icons 2>/dev/null || true
fi

echo ""
echo "========================================="
echo "Installation complete!"
echo "========================================="
echo ""
echo "You can now launch 'Virtual Mic Soundboard' from your application menu"
echo "or run: $INSTALL_DIR/run_soundboard.sh"
echo ""
echo "To uninstall, run: $INSTALL_DIR/uninstall.sh"
echo ""
