from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import mido


@dataclass
class TimedMidiEvent:
    delta_us: int
    message: mido.Message


@dataclass
class LoadedMidi:
    events: List[TimedMidiEvent]
    total_us: int
    title: str


def load_midi_file(path: str) -> LoadedMidi:
    midi_path = Path(path)
    midi = mido.MidiFile(path)
    merged = mido.merge_tracks(midi.tracks)

    tempo = 500000
    events: List[TimedMidiEvent] = []
    total_us = 0

    for message in merged:
        delta_us = int(mido.tick2second(message.time, midi.ticks_per_beat, tempo) * 1_000_000)
        total_us += delta_us
        if message.type == "set_tempo":
            tempo = message.tempo
            continue
        if message.is_meta:
            continue
        events.append(TimedMidiEvent(delta_us=delta_us, message=message))

    return LoadedMidi(events=events, total_us=total_us, title=midi_path.name)
