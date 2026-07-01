from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
from typing import List

from protocol import OplWrite


VGM_SAMPLE_RATE = 44_100


@dataclass
class OplStreamEvent:
    delta_us: int
    writes: List[OplWrite]


@dataclass
class LoadedVgm:
    events: List[OplStreamEvent]
    total_us: int
    title: str


def load_vgm_file(path: str) -> LoadedVgm:
    file_path = Path(path)
    raw = file_path.read_bytes()
    data = gzip.decompress(raw) if file_path.suffix.lower() == ".vgz" else raw
    if data[:4] != b"Vgm ":
        raise ValueError("不是有效的 VGM/VGZ 文件")

    version = _u32(data, 0x08)
    data_offset = _u32(data, 0x34)
    ym3812_clock = _u32(data, 0x50)
    ymf262_clock = _u32(data, 0x5C)
    opl2_compat_mode = ym3812_clock != 0 and ymf262_clock == 0
    data_start = 0x34 + data_offset if version >= 0x00000150 and data_offset else 0x40

    events: List[OplStreamEvent] = []
    pending_delay_us = 0
    pending_writes: List[OplWrite] = []
    total_us = 0
    pos = data_start

    while pos < len(data):
        cmd = data[pos]
        pos += 1

        if cmd == 0x66:
            break

        if cmd == 0x61:
            wait_samples = _u16(data, pos)
            pos += 2
            wait_us = _samples_to_us(wait_samples)
            pending_delay_us = _flush_pending(events, pending_writes, pending_delay_us)
            pending_delay_us += wait_us
            total_us += wait_us
            continue

        if cmd == 0x62:
            wait_us = _samples_to_us(735)
            pending_delay_us = _flush_pending(events, pending_writes, pending_delay_us)
            pending_delay_us += wait_us
            total_us += wait_us
            continue

        if cmd == 0x63:
            wait_us = _samples_to_us(882)
            pending_delay_us = _flush_pending(events, pending_writes, pending_delay_us)
            pending_delay_us += wait_us
            total_us += wait_us
            continue

        if 0x70 <= cmd <= 0x7F:
            wait_us = _samples_to_us((cmd & 0x0F) + 1)
            pending_delay_us = _flush_pending(events, pending_writes, pending_delay_us)
            pending_delay_us += wait_us
            total_us += wait_us
            continue

        if cmd == 0x5A:
            reg = data[pos]
            value = data[pos + 1]
            pos += 2
            if opl2_compat_mode and 0xC0 <= reg <= 0xC8:
                value |= 0x30
            pending_writes.append(OplWrite(0, reg, value))
            continue

        if cmd == 0x5E:
            reg = data[pos]
            value = data[pos + 1]
            pos += 2
            pending_writes.append(OplWrite(0, reg, value))
            continue

        if cmd == 0x5F:
            reg = data[pos]
            value = data[pos + 1]
            pos += 2
            pending_writes.append(OplWrite(1, reg, value))
            continue

        if cmd in (0x4F, 0x50):
            pos += 1
            continue

        if cmd in (0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5B, 0x5C):
            pos += 2
            continue

        if cmd == 0x67:
            if data[pos] != 0x66:
                raise ValueError("VGM 数据块格式错误")
            block_size = _u32(data, pos + 2)
            pos += 6 + block_size
            continue

        if cmd == 0xE0:
            pos += 4
            continue

        raise ValueError(f"暂不支持的 VGM 指令: 0x{cmd:02X}")

    if pending_writes:
        events.append(OplStreamEvent(delta_us=pending_delay_us, writes=list(pending_writes)))

    return LoadedVgm(events=events, total_us=total_us, title=file_path.name)


def _flush_pending(
    events: List[OplStreamEvent],
    pending_writes: List[OplWrite],
    pending_delay_us: int,
) -> int:
    if not pending_writes:
        return pending_delay_us
    events.append(OplStreamEvent(delta_us=pending_delay_us, writes=list(pending_writes)))
    pending_writes.clear()
    return 0


def _samples_to_us(samples: int) -> int:
    return int(round(samples * 1_000_000 / VGM_SAMPLE_RATE))


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")
