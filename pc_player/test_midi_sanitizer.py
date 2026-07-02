from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mido
from midi_sanitizer import sanitize_midi_to_temp_or_bytes

BROKEN_MIDI = Path(r"C:\Users\Ryujou\Desktop\新建文件夹\東方Project官方正作遊戲MIDI文件\東方永夜抄\东方永夜抄ヴォヤージュ.mid")


def run() -> None:
    if not BROKEN_MIDI.is_file():
        print(f"skip: missing sample {BROKEN_MIDI}")
        return

    sanitized = sanitize_midi_to_temp_or_bytes(str(BROKEN_MIDI))
    assert sanitized.name == 'sanitized.mid'
    assert all(ord(ch) < 128 for ch in sanitized.name)

    midi = mido.MidiFile(str(sanitized))
    assert len(midi.tracks) >= 1


if __name__ == '__main__':
    run()
    print('test_midi_sanitizer: ok')
