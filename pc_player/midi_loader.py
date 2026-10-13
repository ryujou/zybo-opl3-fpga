from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import mido
from midi_sanitizer import sanitize_midi_to_temp_or_bytes



@dataclass
class TimedMidiEvent:
    delta_us: int
    message: mido.Message


@dataclass
class LoadedMidi:
    events: List[TimedMidiEvent]
    total_us: int
    title: str
    source_path: str
    parsed_path: str
    sanitized_from: str | None = None


class MidiLoadError(ValueError):
    pass


def _open_midi_with_sanitize(path: str) -> tuple[mido.MidiFile, str, str | None]:
    try:
        return mido.MidiFile(path), path, None
    except Exception as original_exc:
        try:
            sanitized_path = sanitize_midi_to_temp_or_bytes(path)
            return mido.MidiFile(str(sanitized_path)), str(sanitized_path), path
        except Exception as sanitize_exc:
            raise MidiLoadError(
                f"MIDI 解析失败：{path}\n"
                f"原始错误：{original_exc.__class__.__name__}: {original_exc}\n"
                f"sanitize 错误：{sanitize_exc.__class__.__name__}: {sanitize_exc}"
            ) from original_exc


def load_midi_file(path: str) -> LoadedMidi:
    midi_path = Path(path)
    midi, parsed_path, sanitized_from = _open_midi_with_sanitize(path)
    merged = mido.merge_tracks(midi.tracks)

    tempo = 500000
    events: List[TimedMidiEvent] = []
    total_us = 0
    pending_delta_us = 0

    for message in merged:
        delta_us = int(mido.tick2second(message.time, midi.ticks_per_beat, tempo) * 1_000_000)
        total_us += delta_us
        pending_delta_us += delta_us
        if message.type == "set_tempo":
            tempo = message.tempo
            continue
        if message.is_meta:
            continue
        events.append(TimedMidiEvent(delta_us=pending_delta_us, message=message))
        pending_delta_us = 0

    return LoadedMidi(
        events=events,
        total_us=total_us,
        title=midi_path.name,
        source_path=str(midi_path),
        parsed_path=parsed_path,
        sanitized_from=sanitized_from,
    )
