#!/bin/bash
# AppImage builder for Virtual Mic Soundboard
# This script packages the soundboard as a portable AppImage

set -e

APP_NAME="VirtualMicSoundboard"
VERSION="1.0.1"
ARCH="x86_64"

# Get the project root directory (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "Building AppImage for $APP_NAME v$VERSION..."

# Create AppDir structure
APPDIR="$ROOT_DIR/$APP_NAME.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy application files
echo "Copying application files..."
cp src/soundboard.py "$APPDIR/usr/bin/"
cp src/settings.py "$APPDIR/usr/bin/"
cp requirements.txt "$APPDIR/usr/bin/"
cp assets/icon.png "$APPDIR/usr/bin/icon.png"
cp -r assets "$APPDIR/usr/"

# Icon for system integration
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/soundboard.png"

# Root icons for AppImage (must match Icon= name in desktop file)
cp assets/icon.png "$APPDIR/icon.png"
cp assets/icon.png "$APPDIR/.DirIcon"

# Determine python version
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PACKAGES="$APPDIR/usr/lib/python$PY_VER/site-packages"
mkdir -p "$SITE_PACKAGES"

# Install dependencies into AppDir at BUILD TIME
echo "Bundling dependencies for Python $PY_VER..."
pip3 install -r requirements.txt --target "$SITE_PACKAGES" --upgrade

# Create AppRun script
cat > "$APPDIR/AppRun" << EOF
#!/bin/bash
APPDIR="\$(dirname "\$(readlink -f "\$0")")"
export PATH="\$APPDIR/usr/bin:\$PATH"
export LD_LIBRARY_PATH="\$APPDIR/usr/lib:\$LD_LIBRARY_PATH"

# Dynamic PYTHONPATH based on bundled version
export PYTHONPATH="\$APPDIR/usr/lib/python$PY_VER/site-packages:\$PYTHONPATH"

# Use system Python with bundled packages
cd "\$APPDIR/usr/bin"
exec python3 soundboard.py "\$@"
EOF

chmod +x "$APPDIR/AppRun"

# Create desktop file
cat > "$APPDIR/soundboard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Virtual Mic Soundboard
Comment=Play sounds through a virtual microphone
Exec=soundboard
Icon=icon
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
