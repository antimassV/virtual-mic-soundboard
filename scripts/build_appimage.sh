#!/bin/bash
# AppImage builder for Virtual Mic Soundboard
# This script packages the soundboard as a portable AppImage
# Updated to bundle libportaudio and libsndfile

set -e

APP_NAME="VirtualMicSoundboard"
VERSION="1.0.2"
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

# -------------------------------------------------------------------------
# BUNDLE SYSTEM LIBRARIES (Fix for missing .so files)
# -------------------------------------------------------------------------
echo "Bundling system shared libraries..."

# Helper function to find and copy a library by name
# Uses 'ldconfig' to find the path, 'cp -L' to dereference symlinks (copy the actual file)
copy_lib() {
    local lib_name_pattern=$1
    # Find the library path. Grep filters, head takes the first match, cut extracts path.
    local lib_path=$(ldconfig -p | grep "$lib_name_pattern" | head -n 1 | cut -d ">" -f 2 | xargs)
    
    if [ -n "$lib_path" ] && [ -f "$lib_path" ]; then
        echo "  -> Bundling $lib_name_pattern from $lib_path"
        cp -L "$lib_path" "$APPDIR/usr/lib/"
    else
        echo "  !! WARNING: Could not find system library matching: $lib_name_pattern"
        echo "     (The AppImage might fail to run on systems without this library)"
    fi
}

# 1. Core Audio Libraries
copy_lib "libportaudio.so.2"
copy_lib "libsndfile.so.1"

# 2. Dependencies for libsndfile (Vorbis, OGG, FLAC support)
copy_lib "libvorbis.so"
copy_lib "libvorbisenc.so"
copy_lib "libogg.so"
copy_lib "libflac.so"
copy_lib "libopus.so"
copy_lib "libmpg123.so"  # For MP3 support if available

# 3. System helpers often needed by Python CFFI (used by soundfile/pynput)
copy_lib "libffi.so"

# -------------------------------------------------------------------------

# Install Python dependencies into AppDir at BUILD TIME
echo "Bundling Python dependencies for Python $PY_VER..."
# We use --upgrade to ensure we get fresh wheels (which often contain their own binary libs)
pip3 install -r requirements.txt --target "$SITE_PACKAGES" --upgrade

# Create AppRun script
# Note: LD_LIBRARY_PATH ensures our bundled libs in usr/lib are found first
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
# ARCH=x86_64 explicitly set to avoid errors on some systems
ARCH=$ARCH ./appimagetool-x86_64.AppImage "$APPDIR" "$APP_NAME-$VERSION-$ARCH.AppImage"

echo "AppImage created: $APP_NAME-$VERSION-$ARCH.AppImage"
echo "You can now distribute this file!"