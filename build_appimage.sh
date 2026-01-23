#!/bin/bash
# AppImage builder for Virtual Mic Soundboard
# This script packages the soundboard as a portable AppImage

set -e

APP_NAME="VirtualMicSoundboard"
VERSION="1.0.0"
ARCH="x86_64"

echo "Building AppImage for $APP_NAME v$VERSION..."

# Create AppDir structure
APPDIR="$APP_NAME.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy application files
echo "Copying application files..."
cp soundboard.py "$APPDIR/usr/bin/"
cp requirements.txt "$APPDIR/usr/bin/"
cp icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/soundboard.png"
cp icon.png "$APPDIR/"

# Create AppRun script
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "$0")")"
export PATH="$APPDIR/usr/bin:$PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"
export PYTHONPATH="$APPDIR/usr/lib/python3/site-packages:$PYTHONPATH"

# Use system Python with bundled packages
cd "$APPDIR/usr/bin"

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

exec python3 soundboard.py "$@"
EOF

chmod +x "$APPDIR/AppRun"

# Create desktop file
cat > "$APPDIR/soundboard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Virtual Mic Soundboard
Comment=Play sounds through a virtual microphone
Exec=soundboard
Icon=soundboard
Categories=Audio;AudioVideo;
Terminal=false
EOF

cp "$APPDIR/soundboard.desktop" "$APPDIR/usr/share/applications/"

# Download appimagetool if not present
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x appimagetool-x86_64.AppImage
fi

# Build AppImage
echo "Building AppImage..."
ARCH=$ARCH ./appimagetool-x86_64.AppImage "$APPDIR" "$APP_NAME-$VERSION-$ARCH.AppImage"

echo "AppImage created: $APP_NAME-$VERSION-$ARCH.AppImage"
echo "You can now distribute this file!"
