#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout

# ============================================================================
# Configuration Constants
# ============================================================================

# Use persistent user configuration directory
CONFIG_DIR = os.path.expanduser("~/.config/virtual-mic-soundboard")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Try to migrate old config if it exists and new one doesn't
_OLD_LOCAL_CONFIG = "soundboard_config.json"
if not os.path.exists(CONFIG_FILE) and os.path.exists(_OLD_LOCAL_CONFIG):
    try:
        shutil.copy2(_OLD_LOCAL_CONFIG, CONFIG_FILE)
        print(f"Migrated legacy config to {CONFIG_FILE}")
    except Exception as e:
        print(f"Failed to migrate config: {e}")

VIRTUAL_SINK_NAME = "soundboard_virtual_mic"
VIRTUAL_SINK_DESC = "Soundboard Virtual Microphone"
SAMPLE_RATE = 48000
CHANNELS = 2
BLOCKSIZE = 2048
VERSION = "1.1.0"

# Formats libsndfile can decode (m4a/aac are NOT supported by libsndfile).
SUPPORTED_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.opus'}
SUPPORTED_AUDIO_FILTER = "Audio Files (*.mp3 *.wav *.flac *.ogg *.opus);;All Files (*)"

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SoundEntry:
    """Represents a single sound in the soundboard."""
    file_path: str
    name: str = ""
    hotkey: str = ""
    volume: float = 1.0

    # Dynamic state (not saved)
    sound_id: Optional[int] = None
    is_paused: bool = False

    def __post_init__(self):
        if not self.name:
            self.name = Path(self.file_path).stem

    def to_dict(self):
        """Convert to dictionary for clean serialization."""
        return {
            'file_path': self.file_path,
            'name': self.name,
            'hotkey': self.hotkey,
            'volume': self.volume
        }

@dataclass
class AppConfig:
    """Application configuration."""
    sounds_directory: str = str(Path.home() / "Music")
    sounds: List[Dict] = field(default_factory=list) # Type hint is loose here
    overlap_audio: bool = True
    mute_mic_while_playing: bool = True
    master_volume: float = 1.0
    window_geometry: Dict = field(default_factory=dict)
    virtual_sink_name: str = VIRTUAL_SINK_NAME

    def save(self, path: str = CONFIG_FILE):
        # Create a clean dictionary for saving
        data = asdict(self)

        # Fix sounds list: convert SoundEntry objects to dicts if needed
        # because asdict might recursively convert, but we want control
        # or in case 'sounds' contains mixed types during runtime
        clean_sounds = []
        for s in self.sounds:
            if hasattr(s, 'to_dict'):
                clean_sounds.append(s.to_dict())
            elif isinstance(s, dict):
                clean_sounds.append(s)
            else:
                # Fallback for dataclass objects w/o to_dict
                try:
                    clean_sounds.append(asdict(s))
                except:
                    pass

        data['sounds'] = clean_sounds

        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Configuration saved to {path}")
        except Exception as e:
            print(f"Error saving config: {e}")

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> 'AppConfig':
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                print(f"Error loading config: {e}")
        return cls()

# ============================================================================
# AppImage Integration
# ============================================================================

class AppImageIndicator(QDialog):
    """A window showing that the AppImage is active."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AppImage Environment")
        # Standard window flags, keep on top so it's noticed
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        # Remove emoji, standard text
        self.label = QLabel("AppImage Environment Active\nFiles are persistent relative to the AppImage")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.label)

        # Add OK button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.close)
        layout.addWidget(self.ok_btn)

        self.resize(350, 150)

        # Center on screen
        screen_geo = QApplication.primaryScreen().geometry()
        x = (screen_geo.width() - self.width()) // 2
        y = (screen_geo.height() - self.height()) // 2
        self.move(x, y)

def integrate_appimage():
    """automatically create/update a desktop entry when running as AppImage."""
    appimage_path = os.environ.get('APPIMAGE')
    if not appimage_path:
        return None

    desktop_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(desktop_dir, exist_ok=True)
    desktop_file = os.path.join(desktop_dir, "virtual-mic-soundboard.desktop")

    # Correctly identify icon source
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_src_options = [
        os.path.join(script_dir, "..", "assets", "icon.png"),
        os.path.join(script_dir, "assets", "icon.png"),
        os.path.join(script_dir, "icon.png"),
        "/usr/share/icons/hicolor/256x256/apps/soundboard.png" # Fallback within AppImage mount
    ]

    icon_src = None
    for opt in icon_src_options:
        if os.path.exists(opt):
            icon_src = opt
            break

    # Standard destination for system icons
    icon_dest_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
    os.makedirs(icon_dest_dir, exist_ok=True)
    icon_dest = os.path.join(icon_dest_dir, "virtual-mic-soundboard.png")

    # FORCE ICON REPLACEMENT if running from AppImage
    if icon_src:
        try:
            # 1. Direct copy
            shutil.copy2(icon_src, icon_dest)
            print(f"Icon updated: {icon_dest}")

            # 2. Try xdg-icon-resource (standard way) with timeout
            try:
                subprocess.run([
                    "xdg-icon-resource", "install",
                    "--size", "256",
                    "--novendor",
                    icon_src, "virtual-mic-soundboard"
                ], check=False, capture_output=True, timeout=5)
            except subprocess.TimeoutExpired:
                print("xdg-icon-resource timed out")

            # 3. Update icon cache with timeout
            try:
                subprocess.run(["gtk-update-icon-cache", "-f", "-t", os.path.dirname(icon_dest_dir)],
                             check=False, capture_output=True, timeout=5)
            except subprocess.TimeoutExpired:
                print("gtk-update-icon-cache timed out")

        except Exception as e:
            print(f"Failed to update icon: {e}")

    # Always update desktop entry to point to latest AppImage path and icon
    entry = f"""[Desktop Entry]
Type=Application
Name=Virtual Mic Soundboard
Comment=Play sounds through a virtual microphone
Exec="{appimage_path}"
Icon=virtual-mic-soundboard
Categories=Audio;AudioVideo;
Terminal=false
StartupNotify=false
StartupWMClass=soundboard
X-AppImage-Version={VERSION}
"""
    try:
        with open(desktop_file, 'w') as f:
            f.write(entry)
        os.chmod(desktop_file, 0o755)

        # Update system cache with timeout
        try:
            subprocess.run(["update-desktop-database", desktop_dir],
                         check=False, capture_output=True, timeout=5)
            print("Desktop entry updated.")
        except subprocess.TimeoutExpired:
            print("update-desktop-database timed out")

    except Exception as e:
        print(f"Failed to update desktop entry: {e}")

    # Show indicator window
    indicator = AppImageIndicator()
    indicator.show()
    return indicator
