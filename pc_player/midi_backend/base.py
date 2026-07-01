from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MidiBuildResult:
    data: bytes
    event_count: int
    write_count: int
    total_delay_us: int
    backend_name: str
    diagnostic: str = ""


class MidiBackendError(RuntimeError):
    pass
