#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import threading
import time
import signal
from pathlib import Path
from typing import Optional, List, Dict, Callable
import queue

# Import custom settings and configuration
from dataclasses import asdict
from settings import (
    check_dependencies, integrate_appimage, AppConfig, SoundEntry,
    CONFIG_FILE, VIRTUAL_SINK_NAME, VIRTUAL_SINK_DESC,
    SAMPLE_RATE, CHANNELS, BLOCKSIZE, VERSION
)

# Check and install dependencies
check_dependencies()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QSlider, QFileDialog, QLineEdit,
    QCheckBox, QTabWidget, QScrollArea, QFrame, QMessageBox, QDialog,
    QGroupBox, QSpinBox, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QStatusBar, QMenuBar, QMenu, QToolBar, QSizePolicy,
    QProgressBar, QInputDialog, QStyle
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSettings, QSize, QEvent, QObject
)
from PyQt6.QtGui import (
    QAction, QIcon, QKeySequence, QFont, QPalette, QColor, QShortcut
)

from pynput import keyboard
from pynput.keyboard import Key, KeyCode
import numpy as np
import soundfile as sf
import sounddevice as sd
import samplerate

# ============================================================================
# Configuration
# ============================================================================



# ============================================================================
# PipeWire Virtual Microphone Manager
# ============================================================================

class PipeWireManager:
    """Manages PipeWire virtual microphone creation and routing."""
    
    def __init__(self, sink_name: str = VIRTUAL_SINK_NAME):
        self.sink_name = sink_name
        self.module_id = None
        self.null_sink_id = None
        
    def check_pipewire(self) -> bool:
        """Check if PipeWire is running."""
        try:
            result = subprocess.run(
                ['pw-cli', 'info', '0'],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def check_pulseaudio_compat(self) -> bool:
        """Check if PulseAudio compatibility layer is available."""
        try:
            result = subprocess.run(
                ['pactl', 'info'],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def create_virtual_sink(self) -> bool:
        """Create a virtual sink for the soundboard."""
        try:
            # First try to unload any existing module with same name
            self.remove_virtual_sink()
            
            # Create null sink using pactl (works with PipeWire's pulse compatibility)
            cmd = [
                'pactl', 'load-module', 'module-null-sink',
                f'sink_name={self.sink_name}',
                f'sink_properties=device.description="{VIRTUAL_SINK_DESC}" node.pause-on-idle=false',
                f'rate={SAMPLE_RATE}',
                f'channels={CHANNELS}',
                'format=float32le'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.module_id = result.stdout.strip()
                print(f"Created virtual sink: {self.sink_name} (module: {self.module_id})")
                return True
            else:
                print(f"Failed to create virtual sink: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error creating virtual sink: {e}")
            return False
    
    def remove_virtual_sink(self):
        """Remove the virtual sink and all associated bridges/loopbacks."""
        try:
            # First, unload any associated loopback modules to prevent glitches
            result = subprocess.run(
                ['pactl', 'list', 'modules', 'short'],
                capture_output=True, text=True, timeout=3
            )
            
            for line in result.stdout.splitlines():
                # Unload everything related to our sink to clean the graph
                if self.sink_name in line:
                    module_id = line.split()[0]
                    subprocess.run(
                        ['pactl', 'unload-module', module_id],
                        capture_output=True, timeout=2
                    )
                    print(f"Cleanup: Unloaded module {module_id}")
            
            self.module_id = None
                    
        except Exception as e:
            print(f"Error during PipeWire cleanup: {e}")
    
    def get_sink_monitor_name(self) -> str:
        """Get the monitor source name for the virtual sink."""
        return f"{self.sink_name}.monitor"
    
    def get_available_sinks(self) -> List[str]:
        """Get list of available audio sinks."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sinks', 'short'],
                capture_output=True, text=True, timeout=5
            )
            sinks = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    sinks.append(parts[1])
            return sinks
        except Exception as e:
            print(f"Error getting sinks: {e}")
            return []
    
    def get_real_mic_sources(self) -> List[str]:
        """Get list of real microphone sources."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sources', 'short'],
                capture_output=True, text=True, timeout=5
            )
            sources = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    # Filter out monitors and our virtual sink
                    if '.monitor' not in name and self.sink_name not in name:
                        sources.append(name)
            return sources
        except Exception as e:
            print(f"Error getting sources: {e}")
            return []
    
    def get_recording_apps(self) -> List[Dict[str, str]]:
        """Get list of applications currently recording audio."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'source-outputs'],
                capture_output=True, text=True, timeout=5
            )
            
            apps = []
            current_app = {}
            
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('Source Output #'):
                    if current_app:
                        apps.append(current_app)
                    current_app = {'id': line.split('#')[1]}
                elif 'application.name = "' in line:
                    current_app['name'] = line.split('"')[1]
                elif 'media.name = "' in line and 'name' not in current_app:
                    current_app['name'] = line.split('"')[1]
                elif 'application.process.id = "' in line:
                    current_app['pid'] = line.split('"')[1]
                elif line.startswith('Source:'):
                    current_app['source'] = line.split('Source:')[1].strip()
                elif 'Volume:' in line:
                    # Parse volume like 'mono: 65536 / 100% / 0.00 dB'
                    try:
                        parts = line.split('/')
                        if len(parts) >= 2:
                            vol_str = parts[1].strip().replace('%', '')
                            current_app['volume'] = int(vol_str)
                    except:
                        current_app['volume'] = 100
            
            if current_app:
                apps.append(current_app)
            
            # Filter: only show real applications, avoid peak detects and recursive soundboard monitoring
            filtered = []
            for app in apps:
                name = app.get('name', '').lower()
                source = app.get('source', '')
                
                # Basic filters
                if "peak detect" in name: continue
                if "pavucontrol" in name: continue
                
                # Don't show the soundboard itself in the list
                if str(os.getpid()) == app.get('pid', ''): continue
                
                filtered.append(app)
                
            return filtered
        except Exception as e:
            print(f"Error getting recording apps: {e}")
            return []

    def route_app_to_virtual_mic(self, output_id: str):
        """Move a recording stream to the virtual microphone."""
        try:
            subprocess.run(
                ['pactl', 'move-source-output', output_id, self.get_sink_monitor_name()],
                capture_output=True, timeout=5
            )
            return True
        except Exception as e:
            print(f"Error routing app: {e}")
            return False

    def reset_app_routing(self, output_id: str):
        """Move a recording stream back to the default microphone and clear routing preference."""
        try:
            # First, try to get a real hardware microphone (not a monitor)
            real_mics = self.get_real_mic_sources()
            target_source = None
            
            if real_mics:
                # Prefer the default source if it's a real mic
                default_source = self.get_default_source()
                if default_source and default_source in real_mics:
                    target_source = default_source
                else:
                    # Otherwise use the first real mic
                    target_source = real_mics[0]
            else:
                # Fallback to default source even if it's not in our real_mics list
                target_source = self.get_default_source()
            
            if target_source:
                # Move the source-output to the target
                result = subprocess.run(
                    ['pactl', 'move-source-output', output_id, target_source],
                    capture_output=True, text=True, timeout=5
                )
                
                if result.returncode == 0:
                    print(f"Unwired app {output_id} to {target_source}")
                    
                    # Try to clear any stored routing rule for this app
                    # This helps prevent auto-reconnection on app restart
                    try:
                        # Get the application name/binary for this source-output
                        info_result = subprocess.run(
                            ['pactl', 'list', 'source-outputs'],
                            capture_output=True, text=True, timeout=5
                        )
                        
                        # Parse to find the application.name or application.process.binary
                        # and use pactl to unset any stored routing rules
                        # Note: This is best-effort, as PipeWire/PulseAudio may still remember
                        
                    except Exception as e:
                        print(f"Could not clear routing preference: {e}")
                    
                    return True
                else:
                    print(f"Failed to move source-output: {result.stderr}")
                    return False
            else:
                print("No suitable microphone found to unwire to")
                return False
                
        except Exception as e:
            print(f"Error resetting routing: {e}")
            return False

    def set_app_volume(self, output_id: str, volume_percent: int):
        """Set volume for a specific source output (0-200%)."""
        try:
            subprocess.run(
                ['pactl', 'set-source-output-volume', output_id, f"{volume_percent}%"],
                capture_output=True, timeout=5
            )
            return True
        except Exception as e:
            print(f"Error setting app volume: {e}")
            return False

    def get_default_source(self) -> Optional[str]:
        """Get the default system microphone name."""
        try:
            result = subprocess.run(
                ['pactl', 'get-default-source'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None

    def move_own_stream_to_virtual_sink(self) -> bool:
        """Find our own sink-input and move it to our virtual sink."""
        try:
            own_pid = str(os.getpid())
            result = subprocess.run(
                ['pactl', 'list', 'sink-inputs'],
                capture_output=True, text=True, timeout=5
            )
            
            current_id = None
            found = False
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('Sink Input #'):
                    current_id = line.split('#')[1]
                elif f'application.process.id = "{own_pid}"' in line:
                    if current_id:
                        subprocess.run(
                            ['pactl', 'move-sink-input', current_id, self.sink_name],
                            capture_output=True, timeout=5
                        )
                        print(f"Moved soundboard output (ID: {current_id}) to: {self.sink_name}")
                        found = True
            return found
        except Exception as e:
            print(f"Error moving own stream: {e}")
            return False

    def get_virtual_source_id(self) -> Optional[str]:
        """Get the ID of the virtual sink's monitor source."""
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sources', 'short'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == self.get_sink_monitor_name():
                    return parts[0]
            return None
        except:
            return None
    
    def mute_source(self, source_name: str, mute: bool = True):
        """Mute or unmute an audio source."""
        try:
            action = '1' if mute else '0'
            subprocess.run(
                ['pactl', 'set-source-mute', source_name, action],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"Error muting source: {e}")
    
    def mute_all_real_mics(self, mute: bool = True):
        """Mute or unmute all real microphones."""
        for source in self.get_real_mic_sources():
            self.mute_source(source, mute)

    def get_default_speaker(self) -> Optional[str]:
        """Get the default hardware speaker name."""
        try:
            result = subprocess.run(
                ['pactl', 'get-default-sink'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None

    def create_virtual_bridge(self) -> bool:
        """Create a virtual sink and loop it to the hardware speaker."""
        if not self.create_virtual_sink():
            return False
            
        default_speaker = self.get_default_speaker()
        if default_speaker and default_speaker != self.sink_name:
            try:
                # Create a loopback from our virtual sink's monitor to the real speaker
                # This allows the user to hear what's being sent to the virtual mic
                cmd = [
                    'pactl', 'load-module', 'module-loopback',
                    f'source={self.get_sink_monitor_name()}',
                    f'sink={default_speaker}',
                    'latency_msec=50',
                    'description="Soundboard Audio Bridge"'
                ]
                subprocess.run(cmd, capture_output=True, timeout=5)
                print(f"Bridges audio to: {default_speaker}")
            except Exception as e:
                print(f"Error creating audio bridge: {e}")
        return True

# ============================================================================
# Audio Engine
# ============================================================================

class AudioPlayer:
    """Handles audio loading, processing, and playback."""
    
    def __init__(self, sink_name: str = VIRTUAL_SINK_NAME):
        self.sink_name = sink_name
        self.stream = None
        self.active_sounds: Dict[int, Dict] = {}
        self.sound_id_counter = 0
        self.lock = threading.Lock()
        self.master_volume = 1.0
        self.is_playing = False
        self._audio_cache: Dict[str, np.ndarray] = {}
        
    def load_audio(self, file_path: str) -> Optional[np.ndarray]:
        """Load and convert audio file to numpy array."""
        if file_path in self._audio_cache:
            return self._audio_cache[file_path].copy()
        
        try:
            # Use soundfile for all formats including MP3 (if supported by libsndfile)
            samples, source_rate = sf.read(file_path, dtype='float32')
            
            # Ensure stereo
            if len(samples.shape) == 1:
                samples = np.column_stack([samples, samples])
            elif samples.shape[1] == 1:
                samples = np.column_stack([samples, samples])
            
            # Resample if necessary
            if source_rate != SAMPLE_RATE:
                ratio = SAMPLE_RATE / source_rate
                samples = samplerate.resample(samples, ratio, 'sinc_best')
            
            # Ensure float32
            samples = samples.astype(np.float32)
            
            # Cache it
            self._audio_cache[file_path] = samples
            
            return samples.copy()
            
        except Exception as e:
            print(f"Error loading audio {file_path}: {e}")
            return None
    
    def clear_cache(self):
        """Clear the audio cache."""
        self._audio_cache.clear()
    
    def _audio_callback(self, outdata: np.ndarray, frames: int, 
                        time_info, status):
        """Audio stream callback - mixes all active sounds."""
        if status:
            print(f"Audio callback status: {status}")
        
        # Start with silence
        mixed = np.zeros((frames, CHANNELS), dtype=np.float32)
        
        with self.lock:
            finished_ids = []
            
            for sound_id, sound_data in self.active_sounds.items():
                if sound_data.get('paused', False):
                    continue
                    
                samples = sound_data['samples']
                position = sound_data['position']
                volume = sound_data['volume']
                
                remaining = len(samples) - position
                to_copy = min(frames, remaining)
                
                if to_copy > 0:
                    chunk = samples[position:position + to_copy] * volume * self.master_volume
                    mixed[:to_copy] += chunk
                    sound_data['position'] = position + to_copy
                
                if sound_data['position'] >= len(samples):
                    finished_ids.append(sound_id)
            
            # Remove finished sounds
            for sound_id in finished_ids:
                del self.active_sounds[sound_id]
            
            self.is_playing = len(self.active_sounds) > 0
        
        # Soft clipping removed for stability/testing
        # mixed = np.tanh(mixed)
        
        outdata[:] = mixed
    
    def start_stream(self):
        """Start the audio output stream."""
        if self.stream is not None:
            return
        
        try:
            # Find the virtual sink device
            devices = sd.query_devices()
            device_id = None
            
            for i, dev in enumerate(devices):
                if self.sink_name in dev['name'] and dev['max_output_channels'] >= 2:
                    device_id = i
                    break
            
            self.stream = sd.OutputStream(
                device=device_id,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                blocksize=BLOCKSIZE,
                callback=self._audio_callback
            )
            self.stream.start()
            print(f"Audio stream started on device: {device_id}")
            
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            # Try default device
            try:
                self.stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=np.float32,
                    blocksize=BLOCKSIZE,
                    callback=self._audio_callback
                )
                self.stream.start()
                print("Audio stream started on default device")
            except Exception as e2:
                print(f"Error starting on default device: {e2}")
    
    def stop_stream(self):
        """Stop the audio output stream."""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
    
    def play_sound(self, file_path: str, volume: float = 1.0, 
                   overlap: bool = True) -> Optional[int]:
        """Play a sound file."""
        samples = self.load_audio(file_path)
        if samples is None:
            return None
        
        with self.lock:
            if not overlap:
                self.active_sounds.clear()
            
            self.sound_id_counter += 1
            sound_id = self.sound_id_counter
            
            self.active_sounds[sound_id] = {
                'samples': samples,
                'position': 0,
                'volume': volume,
                'file_path': file_path,
                'paused': False
            }
            
            self.is_playing = True
            
        return sound_id
    
    def toggle_pause_sound(self, sound_id: int) -> bool:
        """Toggle pause state of a specific sound. Returns new pause state."""
        with self.lock:
            if sound_id in self.active_sounds:
                current = self.active_sounds[sound_id].get('paused', False)
                self.active_sounds[sound_id]['paused'] = not current
                return not current
        return False

    def stop_sound(self, sound_id: int):
        """Stop a specific sound."""
        with self.lock:
            if sound_id in self.active_sounds:
                del self.active_sounds[sound_id]
            self.is_playing = len(self.active_sounds) > 0

    def set_sound_volume(self, sound_id: int, volume: float):
        """Update volume for an active sound."""
        with self.lock:
            if sound_id in self.active_sounds:
                self.active_sounds[sound_id]['volume'] = volume
    
    def stop_all(self):
        """Stop all sounds."""
        with self.lock:
            self.active_sounds.clear()
            self.is_playing = False
    
    def set_master_volume(self, volume: float):
        """Set master volume (0.0 to 2.0)."""
        self.master_volume = max(0.0, min(2.0, volume))

# ============================================================================
# Global Hotkey Manager
# ============================================================================

class HotkeyManager(QObject):
    """Manages global hotkeys using pynput, communicating with Qt via signals."""
    
    hotkey_triggered = pyqtSignal(str)
    recording_finished = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.hotkeys: set = set()
        self.current_keys: set = set()
        self.triggered_hotkeys: set = set()
        self.listener = None
        self.lock = threading.Lock()
        self.recording = False
        self.recorded_keys: List[str] = []
        
    def _normalize_key(self, key) -> str:
        """Convert pynput key to a highly standardized string representation."""
        try:
            # Special keys (modifiers, arrows, etc)
            if isinstance(key, keyboard.Key):
                name = key.name.lower()
                for mod in ['ctrl', 'alt', 'shift', 'cmd', 'win']:
                    if name.startswith(mod):
                        return mod
                return name
            
            # Character keys (KeyCode)
            if hasattr(key, 'char') and key.char:
                # Common Shifted Symbol Mapping to Base Keys
                # This allows '1' hotkey to trigger even if Shift is held (!)
                shift_map = {
                    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
                    '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
                    '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\',
                    ':': ';', '"': "'", '<': ',', '>': '.', '?': '/'
                }
                char = key.char.lower()
                return shift_map.get(char, char)
            
            # Fallback for VK-only keys
            if hasattr(key, 'vk') and key.vk is not None:
                # Check for standard 0-9 / A-Z VK codes (often works on Linux too)
                if 48 <= key.vk <= 57: return chr(key.vk)
                if 65 <= key.vk <= 90: return chr(key.vk + 32)
                return f"<{key.vk}>"
            
            return str(key).lower().replace('key.', '').split('_')[0]
        except:
            return str(key).lower()
    
    def _on_press(self, key):
        """Handle key press."""
        key_str = self._normalize_key(key)
        
        with self.lock:
            if key_str not in self.current_keys:
                self.current_keys.add(key_str)
            
            if self.recording:
                if key_str not in self.recorded_keys:
                    self.recorded_keys.append(key_str)
                return
            
            # Check for matches (subset matching)
            for hotkey in self.hotkeys:
                if hotkey in self.triggered_hotkeys:
                    continue
                    
                hotkey_parts = set(hotkey.split('+'))
                if hotkey_parts.issubset(self.current_keys):
                    self.hotkey_triggered.emit(hotkey)
                    self.triggered_hotkeys.add(hotkey)
    
    def _on_release(self, key):
        """Handle key release."""
        key_str = self._normalize_key(key)
        
        with self.lock:
            if key_str in self.current_keys:
                self.current_keys.remove(key_str)
            
            # Reset triggered state for any hotkey that had this key as a part
            to_reset = []
            for hotkey in self.triggered_hotkeys:
                if key_str in hotkey.split('+'):
                    to_reset.append(hotkey)
            for h in to_reset:
                self.triggered_hotkeys.discard(h)
            
            if self.recording and not self.current_keys:
                # All keys released, finish recording
                self.recording = False
                hotkey = '+'.join(self.recorded_keys)
                self.recording_finished.emit(hotkey)
                self.recorded_keys.clear()
    
    def start(self):
        """Start listening for hotkeys."""
        if self.listener is None:
            self.listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self.listener.start()
    
    def stop(self):
        """Stop listening for hotkeys."""
        if self.listener is not None:
            self.listener.stop()
            self.listener.join(timeout=1.0)
            self.listener = None
    
    def _normalize_hotkey_string(self, hotkey: str) -> str:
        """Standardize a hotkey string using the same logic as key events."""
        parts = hotkey.lower().split('+')
        normalized = []
        for p in parts:
            p = p.strip()
            # Standardize modifiers
            for mod in ['ctrl', 'alt', 'shift', 'cmd', 'win']:
                if p.startswith(mod):
                    p = mod
                    break
            normalized.append(p)
        return '+'.join(sorted(normalized))

    def register(self, hotkey: str):
        """Register a hotkey string."""
        if not hotkey: return
        with self.lock:
            self.hotkeys.add(self._normalize_hotkey_string(hotkey))
    
    def unregister(self, hotkey: str):
        """Unregister a hotkey string."""
        if not hotkey: return
        with self.lock:
            self.hotkeys.discard(self._normalize_hotkey_string(hotkey))
    
    def clear_all(self):
        """Clear all registered hotkeys."""
        with self.lock:
            self.hotkeys.clear()
    
    def start_recording(self):
        """Start recording a hotkey combination."""
        with self.lock:
            self.recording = True
            self.recorded_keys.clear()
            self.current_keys.clear()

# ============================================================================
# Sound Button Widget
# ============================================================================

class SoundButton(QFrame):
    """A button widget representing a sound in the soundboard."""
    
    hotkey_changed = pyqtSignal(str, str)  # old_hotkey, new_hotkey
    removed = pyqtSignal(object)  # self
    play_requested = pyqtSignal(object)  # self
    
    def __init__(self, sound: SoundEntry, parent=None):
        super().__init__(parent)
        self.sound = sound
        self.setup_ui()
    
    def setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setMinimumSize(150, 120)
        self.setMaximumSize(200, 150)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Sound name
        self.name_label = QLabel(self.sound.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.name_label)
        
        # Play button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setMinimumHeight(35)
        self.play_btn.clicked.connect(self.on_play_clicked)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        layout.addWidget(self.play_btn)
        
        # Pause button
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setMinimumHeight(25)
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        self.pause_btn.setVisible(False)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        layout.addWidget(self.pause_btn)
        
        # Hotkey display/button
        hotkey_layout = QHBoxLayout()
        
        self.hotkey_btn = QPushButton(self.sound.hotkey or "Set Hotkey")
        self.hotkey_btn.setMinimumHeight(25)
        self.hotkey_btn.clicked.connect(self.record_hotkey)
        self.hotkey_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        hotkey_layout.addWidget(self.hotkey_btn)
        
        # Clear hotkey button
        self.clear_hotkey_btn = QPushButton("✕")
        self.clear_hotkey_btn.setMaximumWidth(25)
        self.clear_hotkey_btn.setMinimumHeight(25)
        self.clear_hotkey_btn.clicked.connect(self.clear_hotkey)
        self.clear_hotkey_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        hotkey_layout.addWidget(self.clear_hotkey_btn)
        
        layout.addLayout(hotkey_layout)
        
        # Volume slider
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Vol:"))
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(int(self.sound.volume * 100))
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel(f"{int(self.sound.volume * 100)}%")
        self.volume_label.setMinimumWidth(35)
        volume_layout.addWidget(self.volume_label)
        
        layout.addLayout(volume_layout)
        
        # Remove button
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setMaximumHeight(20)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #9e9e9e;
                color: white;
                border-radius: 2px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #757575;
            }
        """)
        layout.addWidget(self.remove_btn)
    
    def on_volume_changed(self, value):
        self.sound.volume = value / 100.0
        self.volume_label.setText(f"{value}%")
        # If sound is active, update its volume in the player
        if self.sound.sound_id is not None:
            self.window().audio_player.set_sound_volume(self.sound.sound_id, self.sound.volume)

    def on_play_clicked(self):
        if self.sound.sound_id is not None:
            # If playing, stop it
            self.window().stop_sound(self)
        else:
            # If not playing, start it
            self.play_requested.emit(self)
            
    def on_pause_clicked(self):
        if self.sound.sound_id is not None:
            paused = self.window().audio_player.toggle_pause_sound(self.sound.sound_id)
            self.sound.is_paused = paused
            if paused:
                self.pause_btn.setText("▶ Resume")
                self.pause_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 4px; font-weight: bold;")
            else:
                self.pause_btn.setText("⏸ Pause")
                self.pause_btn.setStyleSheet("background-color: #FF9800; color: white; border-radius: 4px; font-weight: bold;")

    def set_playing(self, sound_id, playing=True):
        self.sound.sound_id = sound_id
        if playing:
            self.play_btn.setText("⏹ Stop")
            self.play_btn.setStyleSheet("background-color: #f44336; color: white; border-radius: 4px; font-weight: bold; font-size: 14px;")
            self.pause_btn.setVisible(True)
            self.pause_btn.setText("⏸ Pause")
            self.pause_btn.setStyleSheet("background-color: #FF9800; color: white; border-radius: 4px; font-weight: bold;")
            self.sound.is_paused = False
        else:
            self.play_btn.setText("▶ Play")
            self.play_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 4px; font-weight: bold; font-size: 14px;")
            self.pause_btn.setVisible(False)
            self.sound.sound_id = None
            self.sound.is_paused = False
    
    def record_hotkey(self):
        self.hotkey_btn.setText("Press keys...")
        self.hotkey_btn.setEnabled(False)
        # Signal to main window to start recording
        self.window().start_hotkey_recording(self)
    
    def set_hotkey(self, hotkey: str):
        old_hotkey = self.sound.hotkey
        self.sound.hotkey = hotkey
        self.hotkey_btn.setText(hotkey or "Set Hotkey")
        self.hotkey_btn.setEnabled(True)
        self.hotkey_changed.emit(old_hotkey, hotkey)
    
    def clear_hotkey(self):
        old_hotkey = self.sound.hotkey
        self.sound.hotkey = ""
        self.hotkey_btn.setText("Set Hotkey")
        self.hotkey_changed.emit(old_hotkey, "")
    
    def cancel_recording(self):
        self.hotkey_btn.setText(self.sound.hotkey or "Set Hotkey")
        self.hotkey_btn.setEnabled(True)

# ============================================================================
# Main Window
# ============================================================================

class SoundboardWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize components
        self.config = AppConfig.load()
        self.pw_manager = PipeWireManager(self.config.virtual_sink_name)
        self.audio_player = AudioPlayer(self.config.virtual_sink_name)
        self.hotkey_manager = HotkeyManager()
        
        self.sound_buttons: List[SoundButton] = []
        self.recording_button: Optional[SoundButton] = None
        self.mic_muted = False
        
        self.setup_ui()
        self.setup_audio()
        self.load_sounds()
        self.setup_hotkeys()
        
        # Connect Hotkey Signals
        self.hotkey_manager.hotkey_triggered.connect(self.on_hotkey_triggered)
        self.hotkey_manager.recording_finished.connect(self.finish_hotkey_recording)
        
        self.hotkey_manager.start()
        
        # Debounce timer for app volume
        self._vol_timer = QTimer(self)
        self._vol_timer.setSingleShot(True)
        
        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(500)
    
    def setup_ui(self):
        self.setWindowTitle("Virtual Mic Soundboard")
        self.setMinimumSize(800, 600)
        # Match WMClass for dock grouping
        self.setObjectName("soundboard")
        
        # Set icon
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Restore window geometry
        if self.config.window_geometry:
            try:
                self.setGeometry(
                    self.config.window_geometry.get('x', 100),
                    self.config.window_geometry.get('y', 100),
                    self.config.window_geometry.get('width', 800),
                    self.config.window_geometry.get('height', 600)
                )
            except:
                pass
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Menu bar
        self.setup_menu()
        
        # Toolbar
        self.setup_toolbar()
        
        # Tab Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Soundboard
        soundboard_tab = QWidget()
        soundboard_layout = QVBoxLayout(soundboard_tab)
        
        # Control panel (moved into soundboard tab)
        control_panel = self.create_control_panel()
        soundboard_layout.addWidget(control_panel)
        
        # Sound buttons area
        sounds_group = QGroupBox("Sounds")
        sounds_layout = QVBoxLayout(sounds_group)
        
        # Scroll area for sound buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.sounds_container = QWidget()
        self.sounds_grid = QGridLayout(self.sounds_container)
        self.sounds_grid.setSpacing(10)
        self.sounds_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        scroll.setWidget(self.sounds_container)
        sounds_layout.addWidget(scroll)
        soundboard_layout.addWidget(sounds_group)
        
        self.tabs.addTab(soundboard_tab, "🔊 Soundboard")
        
        # Tab 2: Routing
        routing_tab = self.create_routing_tab()
        self.tabs.addTab(routing_tab, "🔌 Direct Routing")
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        self.playing_label = QLabel("")
        self.playing_label.setStyleSheet("color: green; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.playing_label)
        
        # Apply dark theme
        self.apply_theme()
    
    def setup_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        add_file_action = QAction("Add Sound File...", self)
        add_file_action.setShortcut("Ctrl+O")
        add_file_action.triggered.connect(self.add_sound_file)
        file_menu.addAction(add_file_action)
        
        add_dir_action = QAction("Add Directory...", self)
        add_dir_action.setShortcut("Ctrl+D")
        add_dir_action.triggered.connect(self.add_directory)
        file_menu.addAction(add_dir_action)
        
        file_menu.addSeparator()
        
        set_dir_action = QAction("Set Sounds Directory...", self)
        set_dir_action.triggered.connect(self.set_sounds_directory)
        file_menu.addAction(set_dir_action)
        
        scan_dir_action = QAction("Scan Sounds Directory", self)
        scan_dir_action.setShortcut("F5")
        scan_dir_action.triggered.connect(self.scan_sounds_directory)
        file_menu.addAction(scan_dir_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Save Configuration", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        clear_all_action = QAction("Clear All Sounds", self)
        clear_all_action.triggered.connect(self.clear_all_sounds)
        edit_menu.addAction(clear_all_action)
        
        clear_cache_action = QAction("Clear Audio Cache", self)
        clear_cache_action.triggered.connect(self.audio_player.clear_cache)
        edit_menu.addAction(clear_cache_action)
        
        # Audio menu
        audio_menu = menubar.addMenu("Audio")
        
        stop_all_action = QAction("Stop All Sounds", self)
        stop_all_action.setShortcut("Escape")
        stop_all_action.triggered.connect(self.stop_all_sounds)
        audio_menu.addAction(stop_all_action)
        
        audio_menu.addSeparator()
        
        recreate_sink_action = QAction("Recreate Virtual Sink", self)
        recreate_sink_action.triggered.connect(self.recreate_virtual_sink)
        audio_menu.addAction(recreate_sink_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        routing_help_action = QAction("Audio Routing Help", self)
        routing_help_action.triggered.connect(self.show_routing_help)
        help_menu.addAction(routing_help_action)
    
    def setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Stop button
        stop_btn = QPushButton("⏹ Stop All")
        stop_btn.clicked.connect(self.stop_all_sounds)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        toolbar.addWidget(stop_btn)
        
        toolbar.addSeparator()
        
        # Add file button
        add_btn = QPushButton("➕ Add Sound")
        add_btn.clicked.connect(self.add_sound_file)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        toolbar.addWidget(add_btn)
        
        # Add folder button
        folder_btn = QPushButton("📁 Add Folder")
        folder_btn.clicked.connect(self.add_directory)
        folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        toolbar.addWidget(folder_btn)
    
    def create_control_panel(self) -> QWidget:
        panel = QGroupBox("Controls")
        layout = QHBoxLayout(panel)
        
        # Directory display
        dir_layout = QVBoxLayout()
        dir_layout.addWidget(QLabel("Sounds Directory:"))
        
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.config.sounds_directory)
        self.dir_edit.setReadOnly(True)
        dir_row.addWidget(self.dir_edit)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.set_sounds_directory)
        dir_row.addWidget(browse_btn)
        
        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self.scan_sounds_directory)
        dir_row.addWidget(scan_btn)
        
        dir_layout.addLayout(dir_row)
        layout.addLayout(dir_layout)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(sep)
        
        # Options
        options_layout = QVBoxLayout()
        
        self.overlap_check = QCheckBox("Allow Audio Overlap")
        self.overlap_check.setChecked(self.config.overlap_audio)
        self.overlap_check.toggled.connect(self.on_overlap_changed)
        options_layout.addWidget(self.overlap_check)
        
        self.mute_mic_check = QCheckBox("Mute Real Mic While Playing")
        self.mute_mic_check.setChecked(self.config.mute_mic_while_playing)
        self.mute_mic_check.toggled.connect(self.on_mute_mic_changed)
        options_layout.addWidget(self.mute_mic_check)
        
        layout.addLayout(options_layout)
        
        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(sep2)
        
        # Master volume
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Master Volume:"))
        
        vol_row = QHBoxLayout()
        self.master_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.master_volume_slider.setRange(0, 200)
        self.master_volume_slider.setValue(int(self.config.master_volume * 100))
        self.master_volume_slider.valueChanged.connect(self.on_master_volume_changed)
        vol_row.addWidget(self.master_volume_slider)
        
        self.master_volume_label = QLabel(f"{int(self.config.master_volume * 100)}%")
        self.master_volume_label.setMinimumWidth(40)
        vol_row.addWidget(self.master_volume_label)
        
        volume_layout.addLayout(vol_row)
        layout.addLayout(volume_layout)
        
        return panel
    
    def apply_theme(self):
        """Apply dark theme to the application."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
            }
            QSlider::groove:horizontal {
                background: #555555;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                background: #3c3c3c;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #666666;
                border-radius: 6px;
                min-height: 20px;
            }
            QStatusBar {
                background-color: #1e1e1e;
            }
            QMenuBar {
                background-color: #1e1e1e;
            }
            QMenuBar::item:selected {
                background-color: #3c3c3c;
            }
            QMenu {
                background-color: #2b2b2b;
                border: 1px solid #555555;
            }
            QMenu::item:selected {
                background-color: #4CAF50;
            }
            QToolBar {
                background-color: #1e1e1e;
                border: none;
                spacing: 5px;
                padding: 5px;
            }
        """)
    
    def setup_audio(self):
        """Initialize audio system."""
        # Check PipeWire
        if not self.pw_manager.check_pulseaudio_compat():
            QMessageBox.warning(
                self, "Audio System",
                "PulseAudio/PipeWire not detected!\n"
                "Make sure PipeWire with pipewire-pulse is running."
            )
            return
        
        # Create virtual bridge (sink + loopback to speaker)
        if not self.pw_manager.create_virtual_bridge():
            QMessageBox.warning(
                self, "Virtual Microphone",
                "Failed to create virtual microphone bridge.\n"
                "You may not hear the audio yourself, but it might still work as a mic."
            )
        
        # Wait a moment for sink to be ready
        time.sleep(0.5)
        
        # Start audio stream
        self.audio_player.start_stream()
        self.audio_player.set_master_volume(self.config.master_volume)
        
        # Ensure our own audio is going to the virtual sink
        # We start playing silence immediately so the stream exists to be moved
        # We wait 500ms for PipeWire to register the stream
        QTimer.singleShot(500, lambda: self.pw_manager.move_own_stream_to_virtual_sink())
    
    def load_sounds(self):
        """Load sounds from configuration."""
        for sound_dict in self.config.sounds:
            try:
                sound = SoundEntry(**sound_dict)
                if os.path.exists(sound.file_path):
                    self.add_sound_button(sound)
            except Exception as e:
                print(f"Error loading sound: {e}")
    
    def setup_hotkeys(self):
        """Register all hotkeys in the manager."""
        self.hotkey_manager.clear_all()
        for button in self.sound_buttons:
            if button.sound.hotkey:
                self.hotkey_manager.register(button.sound.hotkey)
    def on_hotkey_triggered(self, hotkey: str):
        """Handle a hotkey being pressed."""
        # Normalize searching hotkey
        normalized_trigger = self.hotkey_manager._normalize_hotkey_string(hotkey)
        
        for button in self.sound_buttons:
            if button.sound.hotkey:
                # Normalize button's hotkey for comparison
                btn_normalized = self.hotkey_manager._normalize_hotkey_string(button.sound.hotkey)
                if btn_normalized == normalized_trigger:
                    self.play_sound(button)
                    if not self.config.overlap_audio:
                        break
        
        # Show debug info in status bar
        combo = '+'.join(sorted(list(self.hotkey_manager.current_keys)))
        self.status_label.setText(f"Keys detected: {combo}")
    
    def add_sound_button(self, sound: SoundEntry):
        """Add a sound button to the grid."""
        button = SoundButton(sound)
        button.play_requested.connect(self.play_sound)
        button.removed.connect(self.remove_sound)
        button.hotkey_changed.connect(self.on_hotkey_changed)
        
        self.sound_buttons.append(button)
        
        # Calculate grid position
        cols = max(1, (self.sounds_container.width() - 20) // 170)
        if cols < 1:
            cols = 4
        
        row = (len(self.sound_buttons) - 1) // cols
        col = (len(self.sound_buttons) - 1) % cols
        
        self.sounds_grid.addWidget(button, row, col)
    
    def refresh_sound_grid(self):
        """Refresh the layout of sound buttons."""
        # Remove all from grid
        for button in self.sound_buttons:
            self.sounds_grid.removeWidget(button)
        
        # Re-add in order
        cols = max(1, (self.sounds_container.width() - 20) // 170)
        if cols < 1:
            cols = 4
        
        for i, button in enumerate(self.sound_buttons):
            row = i // cols
            col = i % cols
            self.sounds_grid.addWidget(button, row, col)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_sound_grid()
    
    def play_sound(self, button: SoundButton):
        """Play a sound."""
        # Mute real mic if enabled
        if self.config.mute_mic_while_playing and not self.mic_muted:
            self.pw_manager.mute_all_real_mics(True)
            self.mic_muted = True
        
        # Play the sound
        sound_id = self.audio_player.play_sound(
            button.sound.file_path,
            button.sound.volume,
            self.config.overlap_audio
        )
        
        if sound_id:
            button.set_playing(sound_id, True)
            self.status_label.setText(f"Playing: {button.sound.name}")

    def stop_sound(self, button: SoundButton):
        """Stop a sound."""
        if button.sound.sound_id is not None:
            self.audio_player.stop_sound(button.sound.sound_id)
            button.set_playing(None, False)
            self.status_label.setText(f"Stopped: {button.sound.name}")
    
    def stop_all_sounds(self):
        """Stop all playing sounds."""
        self.audio_player.stop_all()
        for button in self.sound_buttons:
            button.set_playing(None, False)
        
        # Unmute real mic
        if self.mic_muted:
            self.pw_manager.mute_all_real_mics(False)
            self.mic_muted = False
        
        self.status_label.setText("Stopped")
    
    def remove_sound(self, button: SoundButton):
        """Remove a sound from the soundboard."""
        if button.sound.hotkey:
            self.hotkey_manager.unregister(button.sound.hotkey)
        
        self.sounds_grid.removeWidget(button)
        self.sound_buttons.remove(button)
        button.deleteLater()
        
        self.refresh_sound_grid()
        self.save_config()
    
    def on_hotkey_changed(self, old_hotkey: str, new_hotkey: str):
        """Handle hotkey change."""
        if old_hotkey:
            self.hotkey_manager.unregister(old_hotkey)
        
        if new_hotkey:
            self.hotkey_manager.register(new_hotkey)
        
        self.save_config()
    
    def start_hotkey_recording(self, button: SoundButton):
        """Start recording a hotkey for a button."""
        self.recording_button = button
        self.hotkey_manager.start_recording()
        self.status_label.setText("Press hotkey combination...")
    
    def finish_hotkey_recording(self, hotkey: str):
        """Finish recording a hotkey."""
        if self.recording_button:
            # Check for conflicts
            for button in self.sound_buttons:
                if button != self.recording_button and button.sound.hotkey == hotkey:
                    button.clear_hotkey()
            
            self.recording_button.set_hotkey(hotkey)
            self.recording_button = None
            self.status_label.setText(f"Hotkey set: {hotkey}")
    
    def add_sound_file(self):
        """Add a sound file to the soundboard."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Sound Files",
            self.config.sounds_directory,
            "Audio Files (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac);;All Files (*)"
        )
        
        for file_path in files:
            sound = SoundEntry(file_path=file_path)
            self.add_sound_button(sound)
        
        if files:
            self.save_config()
    
    def add_directory(self):
        """Add all audio files from a directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory",
            self.config.sounds_directory
        )
        
        if directory:
            self.scan_directory(directory)
    
    def scan_directory(self, directory: str):
        """Scan a directory for audio files and add them."""
        audio_extensions = {'.mp3', '.wav', '.flac', '.ogg', '.opus', '.m4a', '.aac'}
        
        added = 0
        for file_name in sorted(os.listdir(directory)):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                ext = os.path.splitext(file_name)[1].lower()
                if ext in audio_extensions:
                    # Check if already added
                    exists = any(b.sound.file_path == file_path for b in self.sound_buttons)
                    if not exists:
                        sound = SoundEntry(file_path=file_path)
                        self.add_sound_button(sound)
                        added += 1
        
        if added:
            self.save_config()
            self.status_label.setText(f"Added {added} sound(s)")
    
    def set_sounds_directory(self):
        """Set the sounds directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Sounds Directory",
            self.config.sounds_directory
        )
        
        if directory:
            self.config.sounds_directory = directory
            self.dir_edit.setText(directory)
            self.save_config()
    
    def scan_sounds_directory(self):
        """Scan the configured sounds directory."""
        self.scan_directory(self.config.sounds_directory)
    
    def clear_all_sounds(self):
        """Clear all sounds from the soundboard."""
        reply = QMessageBox.question(
            self, "Clear All Sounds",
            "Are you sure you want to remove all sounds?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.hotkey_manager.clear_all()
            
            for button in self.sound_buttons[:]:
                self.sounds_grid.removeWidget(button)
                button.deleteLater()
            
            self.sound_buttons.clear()
            self.save_config()
    
    def on_overlap_changed(self, checked: bool):
        self.config.overlap_audio = checked
        self.save_config()
    
    def on_mute_mic_changed(self, checked: bool):
        self.config.mute_mic_while_playing = checked
        self.save_config()
    
    def on_master_volume_changed(self, value: int):
        volume = value / 100.0
        self.config.master_volume = volume
        self.audio_player.set_master_volume(volume)
        self.master_volume_label.setText(f"{value}%")
    
    def create_routing_tab(self) -> QWidget:
        """Create the direct routing tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Direct Application Routing")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        desc = QLabel(
            "Select an application that is currently using a microphone and click 'Wire to Soundboard' "
            "to automatically route the virtual microphone to it."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # App list
        self.routing_list = QListWidget()
        self.routing_list.setStyleSheet("font-size: 14px; padding: 5px;")
        self.routing_list.itemSelectionChanged.connect(self.on_app_selected)
        layout.addWidget(self.routing_list)
        
        # Details / Volume Panel
        self.app_panel = QGroupBox("Selected App Controls")
        panel_layout = QVBoxLayout(self.app_panel)
        self.app_panel.setEnabled(False)
        
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("Output Volume to App:"))
        self.app_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.app_vol_slider.setRange(0, 150)
        self.app_vol_slider.setValue(100)
        self.app_vol_slider.valueChanged.connect(self.on_app_volume_changed)
        vol_layout.addWidget(self.app_vol_slider)
        
        self.app_vol_label = QLabel("100%")
        self.app_vol_label.setMinimumWidth(40)
        vol_layout.addWidget(self.app_vol_label)
        panel_layout.addLayout(vol_layout)
        
        action_layout = QHBoxLayout()
        self.wire_btn = QPushButton("🔌 Wire to Soundboard")
        self.wire_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 30px;")
        self.wire_btn.clicked.connect(self.set_application_routing)
        action_layout.addWidget(self.wire_btn)
        
        self.unwire_btn = QPushButton("📤 Unwire / Reset")
        self.unwire_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; height: 30px;")
        self.unwire_btn.clicked.connect(self.on_unwire_clicked)
        action_layout.addWidget(self.unwire_btn)
        panel_layout.addLayout(action_layout)
        
        layout.addWidget(self.app_panel)
        
        # Refresh button
        self.refresh_routing_btn = QPushButton("🔄 Refresh App List")
        self.refresh_routing_btn.clicked.connect(self.refresh_routing)
        layout.addWidget(self.refresh_routing_btn)
        
        # Auto-refresh timer for list
        self.routing_refresh_timer = QTimer(self)
        self.routing_refresh_timer.timeout.connect(self.refresh_routing)
        
        # Connect tab change to start/stop timer
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        return widget

    def on_tab_changed(self, index):
        """Handle tab change to start/stop list refreshing."""
        if index == 1: # Routing tab
            self.refresh_routing()
            self.routing_refresh_timer.start(2000) # Every 2 seconds
        else:
            self.routing_refresh_timer.stop()

    def refresh_routing(self):
        """Refresh the list of recording applications."""
        try:
            # Remember selected app ID
            item = self.routing_list.currentItem()
            current_app_id = item.data(Qt.ItemDataRole.UserRole) if item else None
            
            # Block signals to prevent selection events during clear/rebuild
            self.routing_list.blockSignals(True)
            self.routing_list.clear() 
            
            apps = self.pw_manager.get_recording_apps()
            monitor_name = self.pw_manager.get_sink_monitor_name()
            monitor_id = self.pw_manager.get_virtual_source_id()
            
            for app in apps:
                app_name = app.get('name', 'Unknown App')
                app_id = app.get('id', '?')
                source = app.get('source', '')
                
                is_wired = source == monitor_name or (monitor_id and source == monitor_id)
                
                status_icon = "🟢" if is_wired else "⚪"
                source_display = "Soundboard" if is_wired else "System Mic"
                item_text = f"{status_icon} {app_name} (Using: {source_display})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, app_id)
                # Store extra data in user role dictionary
                item.setData(Qt.ItemDataRole.UserRole + 1, {
                    'id': app_id,
                    'is_wired': is_wired,
                    'volume': app.get('volume', 100)
                })
                
                if is_wired:
                    item.setForeground(QColor("#4CAF50"))
                
                self.routing_list.addItem(item)
            
            # Reselect previously selected app
            found = False
            for i in range(self.routing_list.count()):
                item = self.routing_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole + 1)
                if data and data.get('id') == current_app_id:
                    self.routing_list.setCurrentRow(i)
                    found = True
                    # Update slider if selected and not being dragged
                    if not self.app_vol_slider.isSliderDown():
                        self.app_vol_slider.blockSignals(True)
                        self.app_vol_slider.setValue(data['volume'])
                        self.app_vol_label.setText(f"{data['volume']}%")
                        self.app_vol_slider.blockSignals(False)
                    break
            
            self.routing_list.blockSignals(False)
            
            # If selection was lost or changed, trigger selection handler manually once
            if found:
                self.on_app_selected()
            else:
                self.app_panel.setEnabled(False)
                    
        except Exception as e:
            self.routing_list.blockSignals(False)
            print(f"Error refreshing routing list: {e}")

    def on_app_selected(self):
        """Handle app selection in list with safety checks."""
        try:
            item = self.routing_list.currentItem()
            if not item:
                self.app_panel.setEnabled(False)
                return
                
            self.app_panel.setEnabled(True)
            data = item.data(Qt.ItemDataRole.UserRole + 1)
            if not data:
                return
                
            # Update UI based on wired status
            if data.get('is_wired'):
                self.wire_btn.setEnabled(False)
                self.unwire_btn.setEnabled(True)
            else:
                self.wire_btn.setEnabled(True)
                self.unwire_btn.setEnabled(False)
                
            # Update volume slider
            self.app_vol_slider.blockSignals(True)
            self.app_vol_slider.setValue(data.get('volume', 100))
            self.app_vol_label.setText(f"{data.get('volume', 100)}%")
            self.app_vol_slider.blockSignals(False)
        except Exception as e:
            print(f"Error in on_app_selected: {e}")
            self.app_panel.setEnabled(False)

    def on_app_volume_changed(self, value: int):
        """Update app volume via pactl with a small debounce to avoid flooding."""
        item = self.routing_list.currentItem()
        if item:
            app_id = item.data(Qt.ItemDataRole.UserRole)
            self.app_vol_label.setText(f"{value}%")
            
            # Disconnect previous connection if any (to avoid multiple calls)
            try:
                self._vol_timer.timeout.disconnect()
            except:
                pass
            
            self._vol_timer.timeout.connect(lambda: self.pw_manager.set_app_volume(app_id, value))
            self._vol_timer.start(50)

    def on_unwire_clicked(self):
        """Reset app routing to default mic."""
        item = self.routing_list.currentItem()
        if item:
            app_id = item.data(Qt.ItemDataRole.UserRole)
            app_name = item.text().split(" (ID:")[0]
            
            if self.pw_manager.reset_app_routing(app_id):
                self.status_label.setText(f"✓ {app_name} unwired and moved to default mic")
                
                # Show informative message about PipeWire behavior
                QMessageBox.information(
                    self,
                    "App Unwired",
                    f"{app_name} has been moved back to your default microphone.\n\n"
                    "Note: PipeWire may remember routing preferences. If the app "
                    "auto-reconnects to the soundboard when restarted, you may need to:\n"
                    "1. Restart the app after unwiring\n"
                    "2. Or use pavucontrol to clear stored preferences"
                )
                
                self.refresh_routing()
            else:
                QMessageBox.warning(
                    self,
                    "Unwire Failed",
                    f"Could not unwire {app_name}. The app may have closed or the routing changed."
                )

    def set_application_routing(self):
        """Wire the selected application to the virtual mic."""
        item = self.routing_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Routing", "Please select an application from the list.")
            return
            
        app_id = item.data(Qt.ItemDataRole.UserRole)
        if self.pw_manager.route_app_to_virtual_mic(app_id):
            self.status_label.setText(f"Application {app_id} wired to virtual microphone")
            self.refresh_routing()
        else:
            QMessageBox.critical(self, "Routing Error", "Failed to route application. Is it still running?")

    def recreate_virtual_sink(self):
        """Recreate the virtual sink."""
        self.audio_player.stop_stream()
        self.pw_manager.create_virtual_sink()
        time.sleep(0.5)
        self.audio_player.start_stream()
        self.status_label.setText("Virtual sink recreated")
    
    def update_status(self):
        """Update status bar and clean up finished sounds."""
        with self.audio_player.lock:
            active_ids = list(self.audio_player.active_sounds.keys())
            
        # Update buttons
        for button in self.sound_buttons:
            if button.sound.sound_id is not None:
                if button.sound.sound_id not in active_ids:
                    button.set_playing(None, False)
        
        if self.audio_player.is_playing:
            self.playing_label.setText("🔊 Playing")
            
            # Unmute real mic when done
            if self.mic_muted and not self.audio_player.is_playing:
                self.pw_manager.mute_all_real_mics(False)
                self.mic_muted = False
        else:
            self.playing_label.setText("")
            
            # Unmute real mic
            if self.mic_muted:
                self.pw_manager.mute_all_real_mics(False)
                self.mic_muted = False
    
    def save_config(self):
        """Save configuration to file."""
        # Update sounds list
        self.config.sounds = [asdict(b.sound) for b in self.sound_buttons]
        
        # Update window geometry
        geo = self.geometry()
        self.config.window_geometry = {
            'x': geo.x(),
            'y': geo.y(),
            'width': geo.width(),
            'height': geo.height()
        }
        
        self.config.save()
    
    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About Virtual Microphone Soundboard",
            """<h2>Virtual Microphone Soundboard</h2>
            <p>A soundboard that plays audio through a virtual microphone.</p>
            <p><b>Features:</b></p>
            <ul>
                <li>Play MP3, WAV, FLAC, OGG, and more</li>
                <li>Global hotkey support</li>
                <li>Audio overlap option</li>
                <li>Automatic mic muting</li>
                <li>Per-sound volume control</li>
            </ul>
            <p><b>Virtual Mic Name:</b><br>
            <code>{0}.monitor</code></p>
            <p>Use pavucontrol or qpwgraph to route the virtual mic to applications.</p>
            """.format(VIRTUAL_SINK_NAME)
        )
    
    def show_routing_help(self):
        """Show audio routing help."""
        QMessageBox.information(
            self, "Audio Routing Help",
            """<h3>How to route audio to applications:</h3>
            
            <h4>Using pavucontrol (PulseAudio Volume Control):</h4>
            <ol>
                <li>Open pavucontrol</li>
                <li>Go to the "Recording" tab</li>
                <li>Find your target application (Discord, OBS, etc.)</li>
                <li>Click the dropdown and select:<br>
                    <b>"Monitor of Soundboard Virtual Microphone"</b></li>
            </ol>
            
            <h4>Using qpwgraph (PipeWire Graph):</h4>
            <ol>
                <li>Open qpwgraph</li>
                <li>Find "Soundboard Virtual Microphone" in the outputs</li>
                <li>Connect its Monitor to your application's input</li>
            </ol>
            
            <h4>Using Helvum:</h4>
            <ol>
                <li>Open Helvum</li>
                <li>Find the soundboard sink</li>
                <li>Connect to your desired application</li>
            </ol>
            
            <p><b>Virtual Sink Name:</b> {0}</p>
            <p><b>Monitor Source:</b> {0}.monitor</p>
            """.format(VIRTUAL_SINK_NAME)
        )
    
    def closeEvent(self, event):
        """Handle window close."""
        # Visual trick: Hide immediately so it looks like it closed instantly
        self.hide()
        QApplication.processEvents()
        
        print("Soundboard: Shutting down...")
        try:
            # 1. Stop audio playback first to stop data flow
            self.audio_player.stop_all()
            self.audio_player.stop_stream()
            
            # 2. Small pause to let audio hardware release
            time.sleep(0.1)
            
            # 3. Clean up hotkeys
            self.hotkey_manager.stop()
            
            # 4. Save config
            self.save_config()
            
            # 5. Restore Mic
            if hasattr(self, 'mic_muted') and self.mic_muted:
                self.pw_manager.mute_all_real_mics(False)
            
            # 6. Purge virtual devices from PipeWire graph
            self.pw_manager.remove_virtual_sink()
        except Exception as e:
            print(f"Cleanup error: {e}")
            
        print("Soundboard: Exiting.")
        event.accept()
        # Kill the entire process tree
        os._exit(0)

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    # Handle signals
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    # The application name should be lowercase and simple for dock matching
    app.setApplicationName("soundboard")
    app.setOrganizationName("Antigravity")
    # This must match the filename of the .desktop file (without suffix)
    app.setDesktopFileName("soundboard")
    app.setQuitOnLastWindowClosed(True)
    
    # Set global application icon
    # Handle both source run (src/../assets) and installed run
    base_dir = os.path.dirname(os.path.abspath(__file__))
    possible_icons = [
        os.path.join(base_dir, "..", "assets", "icon.png"), # From src/
        os.path.join(base_dir, "assets", "icon.png"),       # From root/
        os.path.join(base_dir, "icon.png")                  # Flat/AppImage
    ]
    
    for icon_path in possible_icons:
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    # AppImage Desktop Integration & Icon Refresher
    # AppImage Desktop Integration & Icon Refresher
    # Keep reference to indicator so it doesn't get garbage collected immediately
    _appimage_indicator = None 
    if os.environ.get('APPIMAGE'):
        try:
            _appimage_indicator = integrate_appimage()
        except Exception as e:
            print(f"Failed to integrate AppImage: {e}")
    
    window = SoundboardWindow()
    # Match StartupWMClass for dock grouping
    window.setObjectName("soundboard")
    window.setWindowRole("soundboard")
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
