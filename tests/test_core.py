import json

import numpy as np
import soundfile as sf

from settings import SUPPORTED_EXTENSIONS, AppConfig, SoundEntry
from soundboard import AudioPlayer, HotkeyManager


def test_sound_entry_to_dict_excludes_transient_state():
    entry = SoundEntry(file_path="/tmp/x.wav")
    entry.sound_id = 7
    entry.is_paused = True

    data = entry.to_dict()

    assert "sound_id" not in data
    assert "is_paused" not in data
    assert data == {"file_path": "/tmp/x.wav", "name": "x", "hotkey": "", "volume": 1.0}


def test_config_roundtrip_does_not_persist_transient_state(tmp_path):
    config = AppConfig(
        sounds=[{"file_path": "/tmp/x.wav", "name": "x", "hotkey": "ctrl+1", "volume": 0.5}]
    )
    config_path = tmp_path / "config.json"

    config.save(str(config_path))

    raw = json.loads(config_path.read_text())
    assert raw["sounds"] == config.sounds
    assert all("sound_id" not in s and "is_paused" not in s for s in raw["sounds"])

    loaded = AppConfig.load(str(config_path))
    assert loaded.sounds[0]["volume"] == 0.5
    assert loaded.sounds[0]["hotkey"] == "ctrl+1"


def test_supported_extensions_exclude_libsndfile_unsupported_formats():
    assert ".m4a" not in SUPPORTED_EXTENSIONS
    assert ".aac" not in SUPPORTED_EXTENSIONS
    assert {".mp3", ".wav", ".flac", ".ogg", ".opus"} <= SUPPORTED_EXTENSIONS


def test_hotkey_normalization_is_order_and_case_insensitive():
    manager = HotkeyManager()

    assert manager._normalize_hotkey_string("Ctrl+SHIFT+a") == manager._normalize_hotkey_string("shift+ctrl+A")


def test_hotkey_register_and_unregister():
    manager = HotkeyManager()

    manager.register("Ctrl+1")
    assert manager._normalize_hotkey_string("ctrl+1") in manager.hotkeys

    manager.unregister("ctrl+1")
    assert manager.hotkeys == set()


def test_audio_player_mixes_and_clips(tmp_path):
    wav_path = tmp_path / "tone.wav"
    sf.write(str(wav_path), np.full(1000, 0.9, dtype=np.float32), 48000)

    player = AudioPlayer()
    player.set_master_volume(1.0)
    sound_id = player.play_sound(str(wav_path), volume=1.0, overlap=True)

    assert sound_id is not None
    assert player.is_playing

    out = np.zeros((256, 2), dtype=np.float32)
    player._audio_callback(out, 256, None, None)

    # Loaded audio is stereo, mixed at 0.9 with no boost.
    assert np.allclose(out, 0.9)

    # Force massive gain: output must stay within [-1, 1].
    player.set_master_volume(2.0)
    player.set_sound_volume(sound_id, 2.0)
    player._audio_callback(out, 256, None, None)
    assert out.max() <= 1.0
    assert out.min() >= -1.0


def test_audio_player_removes_finished_sounds(tmp_path):
    wav_path = tmp_path / "short.wav"
    sf.write(str(wav_path), np.zeros(100, dtype=np.float32), 48000)

    player = AudioPlayer()
    sound_id = player.play_sound(str(wav_path), volume=1.0, overlap=True)
    assert sound_id in player.active_sounds

    out = np.zeros((256, 2), dtype=np.float32)
    player._audio_callback(out, 256, None, None)

    assert sound_id not in player.active_sounds
    assert not player.is_playing


def test_audio_player_overlap_false_interrupts(tmp_path):
    wav_path = tmp_path / "long.wav"
    sf.write(str(wav_path), np.zeros(48000, dtype=np.float32), 48000)

    player = AudioPlayer()
    first = player.play_sound(str(wav_path), overlap=True)
    second = player.play_sound(str(wav_path), overlap=False)

    assert first not in player.active_sounds
    assert second in player.active_sounds


def test_audio_player_overlap_true_keeps_both(tmp_path):
    a_wav = tmp_path / "a.wav"
    b_wav = tmp_path / "b.wav"
    sf.write(str(a_wav), np.full(2000, 0.2, dtype=np.float32), 48000)
    sf.write(str(b_wav), np.full(2000, 0.3, dtype=np.float32), 48000)

    player = AudioPlayer()
    first = player.play_sound(str(a_wav), overlap=True)
    second = player.play_sound(str(b_wav), overlap=True)

    assert first in player.active_sounds
    assert second in player.active_sounds

    # The two sounds must be mixed together (0.2 + 0.3 = 0.5).
    out = np.zeros((128, 2), dtype=np.float32)
    player._audio_callback(out, 128, None, None)
    assert np.allclose(out, 0.5, atol=1e-3)


def test_load_audio_returns_stereo_48k(tmp_path):
    mono_path = tmp_path / "mono.wav"
    sf.write(str(mono_path), np.zeros(500, dtype=np.float32), 44100)

    player = AudioPlayer()
    samples = player.load_audio(str(mono_path))

    assert samples is not None
    assert samples.ndim == 2
    assert samples.shape[1] == 2


def test_load_audio_missing_file_returns_none():
    player = AudioPlayer()
    assert player.load_audio("/does/not/exist.wav") is None
