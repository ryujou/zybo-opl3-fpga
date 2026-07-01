from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from midi_loader import LoadedMidi
from opl_allocator import OplMidiSynth
from protocol import OplWrite
from vgm_loader import LoadedVgm, OplStreamEvent

# Keep this at 63 to match the existing streaming protocol limit in protocol.py.
# A preloaded event could theoretically carry up to 255 writes because the count
# field is one byte, but using 63 keeps the file format compatible with both
# streaming and buffered playback firmware parsers.
MAX_WRITES_PER_EVENT = 63


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

        event_count += _append_event(payload, pending_delay_us, writes)
        total_delay_us += pending_delay_us
        pending_delay_us = 0
        write_count += len(writes)

    final_writes = synth.all_notes_off_writes()
    if final_writes:
        event_count += _append_event(payload, 0, final_writes)
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
        event_count += _append_event(payload, event.delta_us, event.writes)
        write_count += len(event.writes)

    return BuiltSong(
        data=bytes(payload),
        event_count=event_count,
        write_count=write_count,
        total_delay_us=total_delay_us,
    )


def _append_event(payload: bytearray, delay_us: int, writes: Iterable[OplWrite]) -> int:
    """Append one logical event, splitting large simultaneous write bursts.

    File format per chunk:
      uint32 delay_us
      uint8  write_count
      repeated write_count times: uint8 bank, uint8 reg, uint8 value

    Some VGMs, including DOOM tracks, contain a very large initialization burst
    before the first wait. The old code tried to store 465 in one byte and
    raised ValueError: byte must be in range(0, 256). Split the burst into
    multiple zero-delay chunks after the first chunk.
    """
    write_list = list(writes)
    if not write_list:
        return 0

    chunk_count = 0
    offset = 0
    first_chunk = True
    while offset < len(write_list):
        chunk = write_list[offset : offset + MAX_WRITES_PER_EVENT]
        chunk_delay = int(delay_us) if first_chunk else 0
        payload.extend(chunk_delay.to_bytes(4, "little", signed=False))
        payload.append(len(chunk))
        for write in chunk:
            payload.extend([write.bank & 0x01, write.reg & 0xFF, write.value & 0xFF])
        offset += len(chunk)
        first_chunk = False
        chunk_count += 1

    return chunk_count
