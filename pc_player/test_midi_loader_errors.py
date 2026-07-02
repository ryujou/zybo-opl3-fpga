from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midi_loader import load_midi_file


BROKEN_MIDI = Path(r"C:\Users\Ryujou\Desktop\新建文件夹\東方Project官方正作遊戲MIDI文件\東方永夜抄\东方永夜抄ヴォヤージュ.mid")


def run() -> None:
    if not BROKEN_MIDI.is_file():
        print(f"skip: missing sample {BROKEN_MIDI}")
        return

    song = load_midi_file(str(BROKEN_MIDI))
    assert song.events, 'sanitized MIDI should still produce events'
    assert song.sanitized_from == str(BROKEN_MIDI)
    assert song.parsed_path.endswith('sanitized.mid')


if __name__ == "__main__":
    run()
    print("test_midi_loader_errors: ok")
