from __future__ import annotations

from midi_backend.base import MidiBuildResult
from midi_loader import LoadedMidi
from opl_allocator import OplMidiSynth
from protocol import OplWrite

MAX_WRITES_PER_EVENT = 63


def _append_event(payload: bytearray, delay_us: int, writes: list[OplWrite]) -> int:
    if not writes:
        return 0

    chunk_count = 0
    offset = 0
    first_chunk = True
    while offset < len(writes):
        chunk = writes[offset : offset + MAX_WRITES_PER_EVENT]
        chunk_delay = int(delay_us) if first_chunk else 0
        payload.extend(chunk_delay.to_bytes(4, "little", signed=False))
        payload.append(len(chunk))
        for write in chunk:
            payload.extend([write.bank & 0x01, write.reg & 0xFF, write.value & 0xFF])
        offset += len(chunk)
        first_chunk = False
        chunk_count += 1

    return chunk_count


def build_with_python_fallback(midi_data: LoadedMidi) -> MidiBuildResult:
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

        write_list = list(writes)
        event_count += _append_event(payload, pending_delay_us, write_list)
        total_delay_us += pending_delay_us
        pending_delay_us = 0
        write_count += len(write_list)

    final_writes = list(synth.all_notes_off_writes())
    if final_writes:
        event_count += _append_event(payload, 0, final_writes)
        write_count += len(final_writes)

    return MidiBuildResult(
        data=bytes(payload),
        event_count=event_count,
        write_count=write_count,
        total_delay_us=total_delay_us,
        backend_name="python fallback",
    )
