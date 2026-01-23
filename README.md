# Virtual Mic Soundboard

A powerful, feature-rich soundboard application for Linux that routes audio through a virtual microphone using PipeWire.

![Soundboard Icon](assets/icon.png)

## Features

- 🎵 **Virtual Microphone**: Play sounds through a virtual microphone that can be used in Discord, OBS, games, and more
- ⌨️ **Global Hotkeys**: Trigger sounds with customizable keyboard shortcuts even when the app is in the background
- 🎚️ **Volume Control**: Individual volume control for each sound plus master volume
- ⏯️ **Pause/Resume**: Pause and resume sounds mid-playback
- 🔄 **Audio Overlap**: Choose whether sounds can play simultaneously or interrupt each other
- 🎤 **Mic Muting**: Automatically mute your real microphone while playing sounds
- 🔊 **Audio Routing**: Built-in tab to manage which applications hear your virtual microphone
- 💾 **Persistent Config**: All settings, sounds, and hotkeys are saved automatically

## System Requirements

- **OS**: Linux (Ubuntu 20.04+, Fedora 34+, or any modern Linux distribution)
- **Audio**: PipeWire (with PulseAudio compatibility layer)
- **Python**: 3.8 or higher
- **Desktop**: X11 or Wayland

## Privacy

**Hotkey Detection:** This app uses `pynput` to detect global hotkeys for triggering sounds. **Keystrokes are NOT recorded or sent anywhere.** They are only used locally on your machine to trigger sound playback when you press the configured hotkey combinations.

## Installation

### Quick Install (Recommended)

```bash
# Download and run the installer
curl -fsSL https://raw.githubusercontent.com/dsadasdasdasdg/virtual-mic-soundboard/main/install.sh | bash
```

### Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/dsadasdasdasdg/virtual-mic-soundboard.git
cd virtual-mic-soundboard
```

2. Run the installation script:
```bash
chmod +x install.sh
./install.sh
```

3. Launch from your application menu or run:
```bash
./run_soundboard.sh
```

### AppImage (Portable)

Download the latest AppImage from [Releases](https://github.com/dsadasdasdasdg/virtual-mic-soundboard/releases):

```bash
# Download the AppImage
wget https://github.com/dsadasdasdasdg/virtual-mic-soundboard/releases/latest/download/VirtualMicSoundboard-x86_64.AppImage

# Make it executable
chmod +x VirtualMicSoundboard-x86_64.AppImage

# Run it
./VirtualMicSoundboard-x86_64.AppImage
```

## Usage

### Adding Sounds

1. Click "Add Sound" in the main window
2. Select an audio file (MP3, WAV, FLAC, or OGG)
3. Optionally set a hotkey by clicking "Set Hotkey" and pressing your desired key combination
4. Adjust the volume slider for individual sound volume

### Setting Up Virtual Microphone

The virtual microphone is created automatically when you launch the app. To use it:

**In Discord/OBS/Games:**
1. Open the application's audio settings
2. Select "Soundboard Virtual Microphone" as your input device

**For Advanced Routing:**
- Use the built-in "Routing" tab to wire specific applications
- Or use `pavucontrol`, `qpwgraph`, or `helvum` for manual routing

### Hotkeys

- Hotkeys work globally, even when the soundboard is minimized
- You can use combinations like `Ctrl+1`, `Alt+Q`, or single keys
- Hotkeys trigger even while holding other keys (e.g., WASD in games)

## Troubleshooting

### Audio stuttering or cutting out
- The app uses a 2048-sample buffer by default for stability
- Ensure PipeWire is running: `systemctl --user status pipewire`

### Hotkeys not working
- Check that no other application is using the same hotkey
- The app uses `pynput` which requires X11 permissions

### Virtual microphone not appearing
- Ensure PipeWire's PulseAudio compatibility is installed:
  ```bash
  # Ubuntu/Debian
  sudo apt install pipewire-pulse
  
  # Fedora
  sudo dnf install pipewire-pulseaudio
  ```

## Uninstallation

```bash
cd /path/to/soundboard
./uninstall.sh
```

Or manually:
```bash
rm -rf ~/.local/share/applications/soundboard.desktop
rm -rf /path/to/soundboard
```

## Development

### Dependencies

- PyQt6
- pynput
- numpy
- soundfile
- sounddevice
- samplerate

### Building from Source

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python3 soundboard.py
```

## License

MIT License - See [LICENSE](LICENSE) for details

## Credits

Created with ❤️ by the Antigravity team

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
