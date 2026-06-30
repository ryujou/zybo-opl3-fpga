from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from midi_loader import LoadedMidi
from opl_allocator import OplMidiSynth
from protocol import OplWrite
from vgm_loader import LoadedVgm, OplStreamEvent


@dataclass
class BuiltSong:
    data: bytes
    event_count: int
    write_count: int
    total_delay_us: int


def build_preloaded_song(song: LoadedMidi | LoadedVgm) -> BuiltSong:
    if isinstance(song, LoadedMidi):
        return _build_from_midi(song)
    if isinstance(song, LoadedVgm):
        return _build_from_opl_events(song.events, song.total_us)
    raise TypeError(f"不支持的曲目类型: {type(song)!r}")


def _build_from_midi(midi_data: LoadedMidi) -> BuiltSong:
    synth = OplMidiSynth()
    payload = bytearray()
    pending_delay_us = 0
    event_count = 0
    write_count = 0
    total_delay_us = 0

    for event in midi_data.events:
        pending_delay_us += event.delta_us
        writes = synth.handle_message(event.message)
        if not writes:
            continue

        _append_event(payload, pending_delay_us, writes)
        total_delay_us += pending_delay_us
        pending_delay_us = 0
        event_count += 1
        write_count += len(writes)

    final_writes = synth.all_notes_off_writes()
    if final_writes:
        _append_event(payload, 0, final_writes)
        event_count += 1
        write_count += len(final_writes)

    return BuiltSong(
        data=bytes(payload),
        event_count=event_count,
        write_count=write_count,
        total_delay_us=total_delay_us,
    )


def _build_from_opl_events(events: Iterable[OplStreamEvent], total_delay_us: int) -> BuiltSong:
    payload = bytearray()
    event_count = 0
    write_count = 0

    for event in events:
        if not event.writes:
            continue
        _append_event(payload, event.delta_us, event.writes)
        event_count += 1
        write_count += len(event.writes)

    return BuiltSong(
        data=bytes(payload),
        event_count=event_count,
        write_count=write_count,
        total_delay_us=total_delay_us,
    )


def _append_event(payload: bytearray, delay_us: int, writes: Iterable[OplWrite]) -> None:
    write_list = list(writes)
    payload.extend(int(delay_us).to_bytes(4, "little", signed=False))
    payload.append(len(write_list))
    for write in write_list:
        payload.extend([write.bank & 0x01, write.reg & 0xFF, write.value & 0xFF])
