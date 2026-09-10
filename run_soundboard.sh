#!/bin/bash
# run_soundboard.sh
# A streamlined launcher that keeps the virtualenv in sync with requirements.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Reinstall dependencies whenever requirements.txt changes.
REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
MARKER="venv/.requirements.sha256"
if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$REQ_HASH" ]; then
    echo "Installing Python dependencies..."
    pip install --upgrade pip >/dev/null
    pip install -r requirements.txt
    echo "$REQ_HASH" > "$MARKER"
fi

# Use a direct log redirect instead of tee to prevent orphaned processes
exec python3 src/soundboard.py "$@" > launch.log 2>&1
