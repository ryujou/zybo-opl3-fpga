from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable, Optional

import serial


SYNC0 = 0x4F
SYNC1 = 0x50
CLI_BAUD = 115200
STREAM_BAUD = 921600

TYPE_HELLO = 0x01
TYPE_ENTER_STREAM = 0x02
TYPE_OPL_EVENT = 0x03
TYPE_STOP = 0x04
TYPE_RESET_OPL = 0x05
TYPE_STATUS = 0x06
TYPE_EXIT_STREAM = 0x07
TYPE_UPLOAD_BEGIN = 0x08
TYPE_UPLOAD_CHUNK = 0x09
TYPE_UPLOAD_END = 0x0A
TYPE_PLAY_BUFFERED = 0x0B
TYPE_ERROR = 0x7F
RESPONSE_MASK = 0x80
UPLOAD_CHUNK_BYTES = 180


@dataclass
class OplWrite:
    bank: int
    reg: int
    value: int


@dataclass
class StreamStatus:
    free_slots: int
    queued_slots: int
    playing: bool


@dataclass
class HelloInfo:
    version_major: int
    version_minor: int
    queue_capacity: int
    stream_baud: int
    cli_baud: int
    preload_capacity: int


class ProtocolError(RuntimeError):
    pass


def _checksum(frame_type: int, payload: bytes) -> int:
    length = len(payload)
    return (frame_type + (length & 0xFF) + ((length >> 8) & 0xFF) + sum(payload)) & 0xFF


def encode_frame(frame_type: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    header = bytes([SYNC0, SYNC1, frame_type, length & 0xFF, (length >> 8) & 0xFF])
    return header + payload + bytes([_checksum(frame_type, payload)])


class ZyboTransport:
    def __init__(self, port: str, timeout: float = 0.3) -> None:
        self.port = port
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None

    def open(self) -> HelloInfo:
        self.serial = serial.Serial(self.port, CLI_BAUD, timeout=self.timeout, write_timeout=self.timeout)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        try:
            self.serial.baudrate = STREAM_BAUD
            hello = self.hello()
        except Exception:
            self.serial.baudrate = CLI_BAUD
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            self.serial.write(b"\rstream\r")
            self.serial.flush()
            time.sleep(0.25)
            self.serial.baudrate = STREAM_BAUD
            hello = self.hello()

        self.enter_stream()
        self.reset_opl()
        self._drain_async_frames()
        return hello

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.exit_stream()
            except Exception:
                pass
            self.serial.close()
            self.serial = None

    def hello(self) -> HelloInfo:
        payload = self._request(TYPE_HELLO)
        if len(payload) < 12:
            raise ProtocolError("HELLO 响应长度不正确")
        preload_capacity = int.from_bytes(payload[12:16], "little") if len(payload) >= 16 else 0
        return HelloInfo(
            version_major=payload[0],
            version_minor=payload[1],
            queue_capacity=payload[2] | (payload[3] << 8),
            stream_baud=int.from_bytes(payload[4:8], "little"),
            cli_baud=int.from_bytes(payload[8:12], "little"),
            preload_capacity=preload_capacity,
        )

    def enter_stream(self) -> None:
        self._request(TYPE_ENTER_STREAM)

    def stop(self) -> None:
        self._request(TYPE_STOP)
        self._drain_async_frames()

    def reset_opl(self) -> None:
        self._request(TYPE_RESET_OPL)
        self._drain_async_frames()

    def exit_stream(self) -> None:
        if self.serial is None:
            return
        self._request(TYPE_EXIT_STREAM)
        self._drain_async_frames()

    def query_status(self) -> StreamStatus:
        payload = self._request(TYPE_STATUS)
        if len(payload) < 5:
            raise ProtocolError("STATUS 响应长度不正确")
        return StreamStatus(
            free_slots=payload[0] | (payload[1] << 8),
            queued_slots=payload[2] | (payload[3] << 8),
            playing=bool(payload[4]),
        )

    def send_event(self, delay_us: int, writes: Iterable[OplWrite]) -> None:
        write_list = list(writes)
        if not write_list:
            return
        if len(write_list) > 63:
            raise ProtocolError("单个事件包含的 OPL 写次数过多")

        payload = bytearray()
        payload.extend(int(delay_us).to_bytes(4, "little", signed=False))
        payload.append(len(write_list))
        for write in write_list:
            payload.extend([write.bank & 0x01, write.reg & 0xFF, write.value & 0xFF])

        self._write_frame(TYPE_OPL_EVENT, bytes(payload))

    def upload_song(self, data: bytes) -> None:
        if not data:
            raise ProtocolError("没有可上传的 OPL 事件数据")
        self._request(TYPE_UPLOAD_BEGIN, len(data).to_bytes(4, "little", signed=False))
        for offset in range(0, len(data), UPLOAD_CHUNK_BYTES):
            chunk = data[offset : offset + UPLOAD_CHUNK_BYTES]
            self._request(TYPE_UPLOAD_CHUNK, chunk)
        self._request(TYPE_UPLOAD_END)

    def play_buffered(self) -> None:
        self._request(TYPE_PLAY_BUFFERED)
        self._drain_async_frames()

    def _request(self, frame_type: int, payload: bytes = b"") -> bytes:
        self._write_frame(frame_type, payload)
        response_type = frame_type | RESPONSE_MASK
        deadline = time.time() + max(self.timeout, 1.0)
        while time.time() < deadline:
            frame = self._read_frame()
            if frame is None:
                continue
            recv_type, recv_payload = frame
            if recv_type == TYPE_ERROR:
                code = recv_payload[0] if recv_payload else -1
                raise ProtocolError(f"板端返回错误码 {code}")
            if recv_type == response_type:
                return recv_payload
        raise ProtocolError("等待板端响应超时")

    def _write_frame(self, frame_type: int, payload: bytes) -> None:
        if self.serial is None:
            raise ProtocolError("串口未打开")
        self.serial.write(encode_frame(frame_type, payload))
        self.serial.flush()

    def _read_exact(self, size: int) -> bytes:
        if self.serial is None:
            raise ProtocolError("串口未打开")
        data = self.serial.read(size)
        if len(data) != size:
            raise TimeoutError("串口读取超时")
        return data

    def _read_frame(self) -> Optional[tuple[int, bytes]]:
        try:
            if self.serial is None:
                return None

            while True:
                first = self.serial.read(1)
                if not first:
                    return None
                if first[0] != SYNC0:
                    continue
                second = self.serial.read(1)
                if not second:
                    return None
                if second[0] == SYNC1:
                    break

            header = self._read_exact(3)
            frame_type = header[0]
            length = header[1] | (header[2] << 8)
            payload = self._read_exact(length) if length else b""
            checksum = self._read_exact(1)[0]
            if checksum != _checksum(frame_type, payload):
                raise ProtocolError("收到的帧校验失败")
            return frame_type, payload
        except TimeoutError:
            return None

    def _drain_async_frames(self) -> None:
        if self.serial is None:
            return
        deadline = time.time() + 0.05
        while time.time() < deadline:
            frame = self._read_frame()
            if frame is None:
                break
