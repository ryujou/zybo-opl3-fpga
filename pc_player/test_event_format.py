from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from midi_loader import load_midi_file
from song_builder import MAX_WRITES_PER_EVENT, build_preloaded_song


def _make_test_midi(path: Path) -> None:
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.Message('program_change', program=12, time=0, channel=0))
    track.append(mido.Message('note_on', note=64, velocity=96, time=0, channel=0))
    track.append(mido.Message('note_off', note=64, velocity=0, time=480, channel=0))
    mid.save(path)


def _iter_events(data: bytes):
    offset = 0
    while offset < len(data):
        assert offset + 5 <= len(data), 'truncated event header'
        delay_us = int.from_bytes(data[offset:offset + 4], 'little', signed=False)
        write_count = data[offset + 4]
        offset += 5
        assert write_count <= 255
        assert write_count <= MAX_WRITES_PER_EVENT
        writes = []
        for _ in range(write_count):
            assert offset + 3 <= len(data), 'truncated write payload'
            bank = data[offset]
            reg = data[offset + 1]
            value = data[offset + 2]
            offset += 3
            assert bank in (0, 1)
            assert 0 <= reg <= 255
            assert 0 <= value <= 255
            writes.append((bank, reg, value))
        assert 0 <= delay_us <= 0xFFFFFFFF
        yield delay_us, writes
    assert offset == len(data)


def run() -> None:
    temp_mid = ROOT / '_tmp_event_format.mid'
    _make_test_midi(temp_mid)
    try:
        song = load_midi_file(str(temp_mid))
        built = build_preloaded_song(song)
        events = list(_iter_events(built.data))
        assert events, 'expected at least one serialized event'
        assert built.write_count >= sum(len(writes) for _, writes in events)
    finally:
        if temp_mid.exists():
            temp_mid.unlink()


if __name__ == '__main__':
    run()
    print('test_event_format: ok')
