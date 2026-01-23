#!/bin/bash
# run_soundboard.sh
# A streamlined launcher.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Use a direct log redirect instead of tee to prevent orphaned processes
exec python3 src/soundboard.py "$@" > launch.log 2>&1
