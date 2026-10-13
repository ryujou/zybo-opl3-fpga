from __future__ import annotations

import tempfile
from pathlib import Path

TARGET_META_LENGTHS = {
    0x51: 3,  # Set Tempo
    0x58: 4,  # Time Signature
    0x59: 2,  # Key Signature
}


class MidiSanitizerError(ValueError):
    pass


class _Cursor:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, count: int) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise MidiSanitizerError("MIDI 数据截断")
        chunk = self.data[self.pos : self.pos + count]
        self.pos += count
        return chunk

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_vlq(self) -> tuple[int, bytes]:
        start = self.pos
        value = 0
        for _ in range(4):
            byte = self.read_byte()
            value = (value << 7) | (byte & 0x7F)
            if not (byte & 0x80):
                return value, self.data[start : self.pos]
        raise MidiSanitizerError("VLQ 长度非法")


def _encode_vlq(value: int) -> bytes:
    if value < 0:
        raise MidiSanitizerError("VLQ 不能为负数")
    buffer = [value & 0x7F]
    value >>= 7
    while value:
        buffer.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(buffer))


def _copy_channel_event(cursor: _Cursor, status: int) -> bytes:
    if 0xC0 <= status <= 0xDF:
        return bytes([status]) + cursor.read(1)
    return bytes([status]) + cursor.read(2)


def _copy_sysex_event(cursor: _Cursor, status: int) -> bytes:
    _, raw_length = cursor.read_vlq()
    length = _decode_vlq(raw_length)
    return bytes([status]) + raw_length + cursor.read(length)


def _decode_vlq(raw: bytes) -> int:
    value = 0
    for byte in raw:
        value = (value << 7) | (byte & 0x7F)
    return value


def _sanitize_track(track_data: bytes) -> bytes:
    cursor = _Cursor(track_data)
    output = bytearray()
    pending_delta = 0
    running_status: int | None = None

    while cursor.remaining() > 0:
        delta, _ = cursor.read_vlq()
        pending_delta += delta
        first = cursor.read_byte()
        status = first

        if first < 0x80:
            if running_status is None or running_status >= 0xF0:
                raise MidiSanitizerError("遇到缺少 running status 的 MIDI 事件")
            status = running_status
            event_data = bytearray([first])
        else:
            event_data = bytearray()

        if status == 0xFF:
            if event_data:
                raise MidiSanitizerError("Meta 事件不能使用 running status")
            meta_type = cursor.read_byte()
            _, raw_length = cursor.read_vlq()
            length = _decode_vlq(raw_length)
            payload = cursor.read(length)
            if meta_type == 0x59 and length != 2:
                payload = b"\x00\x00"
                raw_length = b"\x02"
            elif meta_type == 0x58 and length != 4:
                payload = b"\x04\x02\x18\x08"
                raw_length = b"\x04"
            elif meta_type == 0x51 and length != 3:
                continue
            output.extend(_encode_vlq(pending_delta))
            output.extend(b"\xFF")
            output.append(meta_type)
            output.extend(raw_length)
            output.extend(payload)
            pending_delta = 0
            running_status = None
            continue

        if status in (0xF0, 0xF7):
            if event_data:
                raise MidiSanitizerError("SysEx 事件不能使用 running status")
            _, raw_length = cursor.read_vlq()
            length = _decode_vlq(raw_length)
            payload = cursor.read(length)
            output.extend(_encode_vlq(pending_delta))
            output.append(status)
            output.extend(raw_length)
            output.extend(payload)
            pending_delta = 0
            running_status = None
            continue

        if not 0x80 <= status <= 0xEF:
            raise MidiSanitizerError(f"不支持的 MIDI 状态字节: 0x{status:02X}")

        data_len = 1 if 0xC0 <= status <= 0xDF else 2
        if len(event_data) > data_len:
            raise MidiSanitizerError("MIDI 事件数据长度非法")
        if len(event_data) < data_len:
            event_data.extend(cursor.read(data_len - len(event_data)))

        output.extend(_encode_vlq(pending_delta))
        output.append(status)
        output.extend(event_data)
        pending_delta = 0
        running_status = status

    return bytes(output)


def sanitize_midi_bytes(data: bytes) -> bytes:
    cursor = _Cursor(data)
    header_tag = cursor.read(4)
    if header_tag != b"MThd":
        raise MidiSanitizerError("不是有效的 MIDI 文件头")
    header_length = int.from_bytes(cursor.read(4), "big")
    header_body = cursor.read(header_length)
    if header_length < 6:
        raise MidiSanitizerError("MIDI 文件头长度非法")

    track_count = int.from_bytes(header_body[2:4], "big")
    output = bytearray()
    output.extend(b"MThd")
    output.extend(header_length.to_bytes(4, "big"))
    output.extend(header_body)

    for _ in range(track_count):
        chunk_tag = cursor.read(4)
        if chunk_tag != b"MTrk":
            raise MidiSanitizerError("缺少 MTrk chunk")
        track_length = int.from_bytes(cursor.read(4), "big")
        track_data = cursor.read(track_length)
        sanitized = _sanitize_track(track_data)
        output.extend(b"MTrk")
        output.extend(len(sanitized).to_bytes(4, "big"))
        output.extend(sanitized)

    if cursor.remaining() != 0:
        output.extend(cursor.read(cursor.remaining()))

    return bytes(output)


def sanitize_midi_to_temp_or_bytes(input_path: str) -> Path:
    source = Path(input_path)
    data = source.read_bytes()
    sanitized = sanitize_midi_bytes(data)
    temp_dir = Path(tempfile.mkdtemp(prefix="midi_sanitized_"))
    output_path = temp_dir / "sanitized.mid"
    output_path.write_bytes(sanitized)
    return output_path
