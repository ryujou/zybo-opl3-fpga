from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from midi_backend.base import MidiBackendError
from midi_loader import load_midi_file
from song_builder import build_preloaded_song


def _make_test_midi(path: Path) -> None:
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message('program_change', program=0, time=0, channel=0))
    track.append(mido.Message('note_on', note=60, velocity=100, time=0, channel=0))
    track.append(mido.Message('note_off', note=60, velocity=0, time=480, channel=0))
    mid.save(path)


def run() -> None:
    temp_mid = ROOT / '_tmp_backend_selection.mid'
    _make_test_midi(temp_mid)
    original_backend = config.MIDI_BACKEND
    original_exe = config.MIDI2VGM_EXE_PATH
    original_keep_temp = config.MIDI2VGM_KEEP_TEMP
    original_extra_args = list(config.MIDI2VGM_EXTRA_ARGS)
    original_bank = getattr(config, 'MIDI2VGM_BANK', None)
    original_bank_path = config.MIDI2VGM_BANK_PATH
    try:
        song = load_midi_file(str(temp_mid))

        config.MIDI_BACKEND = 'python'
        built = build_preloaded_song(song)
        assert built.backend_name == 'python fallback'
        assert built.data, 'python backend should produce payload'

        config.MIDI_BACKEND = 'auto'
        config.MIDI2VGM_EXE_PATH = str(ROOT / 'missing_midi2vgm_opl3.exe')
        built = build_preloaded_song(song)
        assert built.backend_name == 'python fallback'
        assert 'fallback to python mapper' in built.diagnostic
        assert 'https://github.com/SudoMaker/midi2vgm' in built.diagnostic

        config.MIDI_BACKEND = 'midi2vgm'
        try:
            build_preloaded_song(song)
        except MidiBackendError as exc:
            message = str(exc)
            assert 'https://github.com/SudoMaker/midi2vgm' in message
            assert 'MIDI2VGM_EXE_PATH' in message or '未找到 midi2vgm_opl3' in message
        else:
            raise AssertionError('midi2vgm mode should fail when executable is missing')
    finally:
        config.MIDI_BACKEND = original_backend
        config.MIDI2VGM_EXE_PATH = original_exe
        config.MIDI2VGM_KEEP_TEMP = original_keep_temp
        config.MIDI2VGM_EXTRA_ARGS = original_extra_args
        config.MIDI2VGM_BANK = original_bank
        config.MIDI2VGM_BANK_PATH = original_bank_path
        if temp_mid.exists():
            temp_mid.unlink()


if __name__ == '__main__':
    run()
    print('test_backend_selection: ok')
