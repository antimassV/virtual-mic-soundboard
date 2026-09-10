#!/bin/bash
# AppImage builder for Virtual Mic Soundboard.
#
# Hardened packaging: a self-contained CPython (python-build-standalone) is
# bundled into the AppImage, so the result does not depend on the target
# machine having a compatible system Python. The previous approach installed
# wheels for the build machine's Python into a shared directory but still ran
# the host's `python3`, which broke whenever the host minor version differed.

set -e

APP_NAME="VirtualMicSoundboard"
ARCH="x86_64"

# Pinned standalone CPython (relocatable, no system Python required).
PYTHON_VERSION="3.11.16"
PBS_TAG="20260901"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PYTHON_VERSION}+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"

APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

# Get the project root directory (one level up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/virtual-mic-soundboard"
mkdir -p "$CACHE_DIR"

# Single source of truth for the app version (embedded in the desktop entry).
VERSION="$(grep -m1 '^VERSION = ' src/settings.py | cut -d '"' -f 2)"

echo "Building AppImage for $APP_NAME v$VERSION..."

APPDIR="$ROOT_DIR/$APP_NAME.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# -------------------------------------------------------------------------
# 1. Application files
# -------------------------------------------------------------------------
echo "Copying application files..."
cp src/soundboard.py "$APPDIR/usr/bin/"
cp src/settings.py "$APPDIR/usr/bin/"
cp requirements.txt "$APPDIR/usr/bin/"
# settings.py/main() resolve the icon relative to the scripts (../assets).
mkdir -p "$APPDIR/usr/assets"
cp assets/icon.png "$APPDIR/usr/assets/icon.png"
cp assets/icon.png "$APPDIR/usr/bin/icon.png"

# Icon for desktop integration.
cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/soundboard.png"

# Root icons for AppImage (must match Icon= name in the desktop file).
cp assets/icon.png "$APPDIR/icon.png"
cp assets/icon.png "$APPDIR/.DirIcon"

# -------------------------------------------------------------------------
# 2. Bundle a self-contained Python interpreter
# -------------------------------------------------------------------------
PYTHON_TARBALL="$CACHE_DIR/cpython-${PYTHON_VERSION}+${PBS_TAG}-install_only_stripped.tar.gz"
if [ ! -f "$PYTHON_TARBALL" ]; then
    echo "Downloading standalone CPython $PYTHON_VERSION..."
    curl -fSL -o "$PYTHON_TARBALL" "$PBS_URL"
fi

echo "Extracting CPython into AppDir..."
mkdir -p "$APPDIR/usr"
tar -xzf "$PYTHON_TARBALL" -C "$APPDIR/usr"

BUNDLED_PY="$APPDIR/usr/python/bin/python3"
if [ ! -x "$BUNDLED_PY" ]; then
    echo "ERROR: bundled interpreter not found at $BUNDLED_PY"
    exit 1
fi

echo "Installing Python dependencies into bundled interpreter..."
"$BUNDLED_PY" -m pip install --no-warn-script-location --upgrade pip
"$BUNDLED_PY" -m pip install --no-warn-script-location --upgrade -r requirements.txt

# Drop pip's cache/wheels to keep the AppImage small.
rm -rf "$APPDIR/usr/python/lib/python"*/site-packages/pip \
       "$APPDIR/usr/python/lib/python"*/site-packages/setuptools \
       "$APPDIR/usr/python/lib/python"*/site-packages/wheel* 2>/dev/null || true

# -------------------------------------------------------------------------
# 3. Bundle native libraries loaded at runtime via dlopen/ctypes
# -------------------------------------------------------------------------
echo "Bundling system shared libraries..."

copy_lib() {
    local pattern=$1
    local path
    path="$(ldconfig -p | grep "$pattern" | head -n 1 | cut -d '>' -f 2 | xargs)"
    if [ -n "$path" ] && [ -f "$path" ]; then
        echo "  -> $pattern from $path"
        cp -L "$path" "$APPDIR/usr/lib/"
    else
        echo "  !! WARNING: no system library matching $pattern (target systems must provide it)"
    fi
}

# sounddevice dlopens libportaudio via ctypes, so it must be present.
# Nothing else needs bundling: the soundfile wheel statically links all of its
# audio codecs, and Python's cffi/libffi is self-contained. Bundling only this
# one library also means LD_LIBRARY_PATH cannot shadow the libraries used by
# helper processes such as pactl.
copy_lib "libportaudio.so.2"

# -------------------------------------------------------------------------
# 4. AppRun launcher
# -------------------------------------------------------------------------
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"

# Do not let the host's Python configuration leak into the bundled runtime.
unset PYTHONHOME PYTHONPATH

export PATH="$HERE/usr/bin:$HERE/usr/python/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"

# Bundled interpreter: no dependency on the host's Python.
cd "$HERE/usr/bin"
exec "$HERE/usr/python/bin/python3" soundboard.py "$@"
EOF

chmod +x "$APPDIR/AppRun"

# -------------------------------------------------------------------------
# 5. Desktop file
# -------------------------------------------------------------------------
cat > "$APPDIR/soundboard.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Virtual Mic Soundboard
Comment=Play sounds through a virtual microphone
Exec=soundboard
Icon=icon
Categories=Audio;AudioVideo;
Terminal=false
StartupWMClass=soundboard
EOF

cp "$APPDIR/soundboard.desktop" "$APPDIR/usr/share/applications/"

# -------------------------------------------------------------------------
# 6. Build the AppImage
# -------------------------------------------------------------------------
APPIMAGETOOL="$CACHE_DIR/appimagetool-$ARCH.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    curl -fSL -o "$APPIMAGETOOL" "$APPIMAGETOOL_URL"
    chmod +x "$APPIMAGETOOL"
fi

echo "Building AppImage..."
# APPIMAGE_EXTRACT_AND_RUN lets appimagetool work without FUSE.
# --no-appstream skips AppStream metadata validation (not needed here).
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$APPIMAGETOOL" --no-appstream \
    "$APPDIR" "$ROOT_DIR/$APP_NAME-$ARCH.AppImage"

echo "AppImage created: $APP_NAME-$ARCH.AppImage"
echo "You can now distribute this file!"
