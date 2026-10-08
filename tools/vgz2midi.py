# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert OPL2/OPL3 2-op VGM/VGZ to ordinary MIDI, using bank 58 GM patches."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import gzip
import json
import math
from pathlib import Path
import struct
import zlib

import mido

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 44100
MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != 9)
OPERATOR_OFFSETS = (0, 1, 2, 8, 9, 10, 16, 17, 18)
MULTIPLIERS = (0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15)
# Bass drum, snare, tom, cymbal and hi-hat in OPL rhythm mode.
RHYTHM = ((6, 3, 35, 16), (7, 3, 38, 8), (8, 0, 45, 4),
          (8, 3, 49, 2), (7, 0, 42, 1))


class ConversionCancelled(Exception):
    pass


@dataclass
class ConversionResult:
    source: Path
    destination: Path
    chip: str
    duration: float
    notes: int
    approximate_notes: int
    channel_approximations: int


def _patch_key(feedback, operators):
    mod, carrier = operators
    # AM/vibrato and carrier level change during playback; they do not select
    # a different instrument. Additive modulator level is also a volume input.
    return (feedback & 15, mod[0] & 63,
            mod[1] & (192 if feedback & 1 else 255), mod[2], mod[3], mod[4] & 7,
            carrier[0] & 63, carrier[1] & 192, carrier[2], carrier[3], carrier[4] & 7)


# This small table is derived from the pinned, GPL-3.0-or-later libADLMIDI
# instrument database; copyright and license are in third_party/libadlmidi.
with Path(__file__).with_name("opl_gm_bank58.json").open(encoding="utf-8") as _file:
    PATCHES = json.load(_file)["patches"]
PATCH_KEYS = tuple(_patch_key(p["feedback"], p["operators"]) for p in PATCHES)


def _patch_distance(a, b):
    distance = 24 * ((a[0] ^ b[0]) & 1) + abs((a[0] >> 1) - (b[0] >> 1)) * 1.5
    for offset in (1, 6):
        x, y = a[offset], b[offset]
        distance += 10 * abs(math.log2(MULTIPLIERS[x & 15] / MULTIPLIERS[y & 15]))
        distance += 10 * bool((x ^ y) & 32) + 3 * bool((x ^ y) & 16)
        distance += 2 * ((a[offset + 1] ^ b[offset + 1]) >> 6).bit_count()
        for index, high_weight, low_weight in ((2, 1, 0.5), (3, 0.5, 1)):
            distance += high_weight * abs((a[offset + index] >> 4) - (b[offset + index] >> 4))
            distance += low_weight * abs((a[offset + index] & 15) - (b[offset + index] & 15))
        distance += 12 * (a[offset + 4] != b[offset + 4])
    if not a[0] & 1 and not b[0] & 1:
        distance += abs((a[2] & 63) - (b[2] & 63)) / 4
    return distance


@lru_cache(maxsize=4096)
def _match_patch(key):
    # Register logs repeat the same patches across notes and channels.
    exact = next((i for i, candidate in enumerate(PATCH_KEYS) if candidate == key), None)
    if exact is not None:
        return exact, False
    index = min((i for i, patch in enumerate(PATCHES) if not patch["drum"]),
                key=lambda i: _patch_distance(key, PATCH_KEYS[i]))
    return index, True


class OplToMidi:
    def __init__(self, chip, clock, title):
        self.chip, self.clock = chip, clock
        self.registers = bytearray(512)
        self.tick = self.last_tick = 0
        self.dirty = set()
        self.active = [None] * 23
        self.owners = [set() for _ in range(16)]
        self.channel_state = [None] * 16
        self.notes = self.approximate_notes = self.channel_approximations = 0
        self.midi = mido.MidiFile(type=0, ticks_per_beat=22050, charset="utf-8")
        self.track = mido.MidiTrack()
        self.midi.tracks.append(self.track)
        self.track.append(mido.MetaMessage("track_name", name=title))
        self.track.append(mido.MetaMessage("set_tempo", tempo=500000))
        self.track.append(mido.Message("sysex", data=(0x7E, 0x7F, 0x09, 0x01)))
        # Explicit ±2-semitone bend range, independent of player/channel history.
        for channel in MELODIC_CHANNELS:
            for control, value in ((101, 0), (100, 0), (6, 2), (38, 0),
                                   (101, 127), (100, 127)):
                self.emit("control_change", channel=channel, control=control, value=value)

    def emit(self, kind, **kwargs):
        self.track.append(mido.Message(kind, time=self.tick - self.last_tick, **kwargs))
        self.last_tick = self.tick

    def release(self, voice):
        previous = self.active[voice]
        if previous is None:
            return
        channel, note = previous
        self.owners[channel].remove(voice)
        self.active[voice] = None
        if not any(self.active[owner][1] == note for owner in self.owners[channel]):
            self.emit("note_off", channel=channel, note=note, velocity=0)

    def configure(self, channel, state):
        old = self.channel_state[channel]
        program, volume, pan, bend = state
        if old is None or old[0] != program:
            self.emit("program_change", channel=channel, program=program)
        for index, control, value in ((1, 7, volume), (2, 10, pan)):
            if old is None or old[index] != value:
                self.emit("control_change", channel=channel, control=control, value=value)
        if old is None or old[3] != bend:
            self.emit("pitchwheel", channel=channel, pitch=bend)
        self.channel_state[channel] = state

    def write(self, register, value):
        if register == 0x104 and value & 63:
            raise ValueError("暂不支持 OPL3 4-op 音色；此转换器支持 2-op 文件")
        if self.registers[register] == value:
            return
        bank, reg = register >> 8, register & 255
        if 0xB0 <= reg <= 0xB8 and self.registers[register] & 32 and not value & 32:
            voice = bank * 9 + reg - 0xB0
            self.sync(voice)
            self.release(voice)
        if register == 0xBD:
            # Preserve gate edges even when multiple writes share one timestamp.
            self.flush()
            for voice in range(6, 9):
                self.release(voice)
            for voice, (_, _, _, bit) in enumerate(RHYTHM, 18):
                if not value & 32 or not value & bit:
                    self.release(voice)
            self.dirty.update(range(6, 9))
            self.dirty.update(range(18, 23))
        self.registers[register] = value
        if register in (1, 0x105):
            self.dirty.update(range(18))
        elif 0xA0 <= reg <= 0xA8 or 0xB0 <= reg <= 0xB8 or 0xC0 <= reg <= 0xC8:
            self.dirty.add(bank * 9 + (reg & 15))
        elif reg & 0xE0 in (0x20, 0x40, 0x60, 0x80, 0xE0):
            offset = reg & 31
            for channel, mod in enumerate(OPERATOR_OFFSETS):
                if offset in (mod, mod + 3):
                    self.dirty.add(bank * 9 + channel)
                    break
        if not bank and self.registers[0xBD] & 32:
            self.dirty.update(range(18, 23))

    def _operator(self, bank, offset):
        values = [self.registers[bank + base + offset] for base in (0x20, 0x40, 0x60, 0x80, 0xE0)]
        if self.chip == "OPL2" and not self.registers[1] & 32:
            values[4] = 0
        return values

    def sync(self, voice):
        if voice >= 18:
            channel, carrier, note, bit = RHYTHM[voice - 18]
            if not self.registers[0xBD] & 32 or not self.registers[0xBD] & bit:
                self.release(voice)
                return
            level = self.registers[0x40 + OPERATOR_OFFSETS[channel] + carrier] & 63
            velocity = max(1, round(127 * 10 ** (-0.75 * level / 40)))
            self.start(voice, 9, note, velocity)
            return
        bank, channel = divmod(voice, 9)
        base = bank * 256
        b0 = self.registers[base + 0xB0 + channel]
        if (not b0 & 32 or (bank and (self.chip == "OPL2" or not self.registers[0x105] & 1))
                or (not bank and channel >= 6 and self.registers[0xBD] & 32)):
            self.release(voice)
            return
        fnum = self.registers[base + 0xA0 + channel] | (b0 & 3) << 8
        if not fnum:
            self.release(voice)
            return
        operators = [self._operator(base, OPERATOR_OFFSETS[channel] + offset) for offset in (0, 3)]
        feedback = self.registers[base + 0xC0 + channel]
        patch_index, approximate = _match_patch(_patch_key(feedback, operators))
        patch = PATCHES[patch_index]
        volume = round(127 * 10 ** (-0.75 * max(0, (operators[1][1] & 63)
                                                   - (patch["operators"][1][1] & 63)) / 40))
        pan = 64
        if self.chip == "OPL3" and self.registers[0x105] & 1:
            routing = feedback & 0x30
            pan = {0x10: 0, 0x20: 127}.get(routing, 64)
            if not routing:
                volume = 0
        if patch["drum"]:
            if not volume:
                self.release(voice)
                return
            self.start(voice, 9, patch["program"], max(1, volume), approximate)
            return
        frequency = fnum * self.clock / (288 if self.chip == "OPL3" else 72) * 2 ** (((b0 >> 2) & 7) - 20)
        pitch = 69 + 12 * math.log2(frequency / 440) - patch["transpose"]
        if not 0 <= pitch <= 127:
            self.release(voice)
            return
        previous = self.active[voice]
        note = round(pitch)
        if previous and previous[0] != 9:
            old = self.channel_state[previous[0]]
            if old[0] == patch["program"] and -2 <= pitch - previous[1] < 2:
                note = previous[1]
        bend = max(-8192, min(8191, round((pitch - note) * 4096)))
        state = (patch["program"], volume, pan, bend)
        if previous and previous[0] != 9 and previous[1] == note:
            midi_channel = previous[0]
            if self.channel_state[midi_channel] == state:
                return
            if len(self.owners[midi_channel]) == 1 and self.channel_state[midi_channel][0] == state[0]:
                self.configure(midi_channel, state)
                return
        self.release(voice)
        midi_channel = next((ch for ch in MELODIC_CHANNELS
                             if self.owners[ch] and self.channel_state[ch] == state), None)
        if midi_channel is None:
            midi_channel = next((ch for ch in MELODIC_CHANNELS if not self.owners[ch]), None)
        if midi_channel is None:
            self.channel_approximations += 1
            midi_channel = min(MELODIC_CHANNELS, key=lambda ch:
                               (self.channel_state[ch][0] != state[0]) * 1000
                               + abs(self.channel_state[ch][1] - volume)
                               + abs(self.channel_state[ch][2] - pan)
                               + abs(self.channel_state[ch][3] - bend) / 64)
        else:
            self.configure(midi_channel, state)
        self.start(voice, midi_channel, note, 127, approximate)

    def start(self, voice, channel, note, velocity, approximate=False):
        if self.active[voice] == (channel, note):
            return
        self.release(voice)
        if not any(self.active[owner][1] == note for owner in self.owners[channel]):
            self.emit("note_on", channel=channel, note=note, velocity=velocity)
            self.notes += 1
            self.approximate_notes += int(approximate)
        self.active[voice] = (channel, note)
        self.owners[channel].add(voice)

    def flush(self):
        for voice in sorted(self.dirty):
            self.sync(voice)
        self.dirty.clear()

    def finish(self, destination):
        self.flush()
        for voice in range(len(self.active)):
            self.release(voice)
        for channel in range(16):
            self.emit("control_change", channel=channel, control=123, value=0)
        self.track.append(mido.MetaMessage("end_of_track", time=self.tick - self.last_tick))
        if not self.notes:
            raise ValueError("文件中没有可转换的 OPL 音符")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.midi.save(destination)


def find_inputs(source):
    source = Path(source)
    if source.is_file():
        return [(source, Path(source.name).with_suffix(".mid"))] if source.suffix.lower() in (".vgm", ".vgz") else []
    return [(file, file.relative_to(source).with_suffix(".mid"))
            for file in sorted(source.rglob("*"))
            if file.is_file() and file.suffix.lower() in (".vgm", ".vgz")]


def convert_file(source, destination, progress=None):
    """Convert one file. A progress callback returning False cancels the conversion."""
    source, destination = Path(source), Path(destination)
    raw = source.read_bytes()
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    if len(data) < 64 or data[:4] != b"Vgm ":
        raise ValueError("不是有效的 VGM/VGZ 文件")
    version, = struct.unpack_from("<I", data, 8)
    offset, = struct.unpack_from("<I", data, 0x34)
    start = 0x34 + offset if version >= 0x150 and offset else 0x40
    if not 0x40 <= start < len(data):
        raise ValueError("VGM 数据起始位置超出文件范围")
    clocks = [(name, struct.unpack_from("<I", data, field)[0])
              for name, field in (("OPL3", 0x5C), ("OPL2", 0x50)) if field + 4 <= start]
    chip, clock = next(((name, clock) for name, clock in clocks if clock & 0x3FFFFFFF), (None, 0))
    if chip is None:
        raise ValueError("文件未声明 OPL2/YM3812 或 OPL3/YMF262 时钟")
    if clock & 0x40000000:
        raise ValueError("暂不支持双芯片 OPL 文件")
    synth = OplToMidi(chip, clock & 0x3FFFFFFF, source.stem)
    waits = {0x62: 735, 0x63: 882}
    pos, commands, ended = start, 0, False
    while pos < len(data):
        if commands % 8192 == 0 and progress is not None:
            if progress((pos - start) / (len(data) - start)) is False:
                raise ConversionCancelled()
        commands += 1
        command_pos = pos
        command = data[pos]
        pos += 1
        if command == 0x66:
            ended = True
            break
        if command in (0x5A, 0x5E, 0x5F, 0x61, 0x64):
            count = 3 if command == 0x64 else 2
            if pos + count > len(data):
                raise ValueError(f"VGM 指令数据不足，位置 0x{command_pos:X}")
            if command in (0x5A, 0x5E, 0x5F):
                if (chip == "OPL2") != (command == 0x5A):
                    raise ValueError("OPL 指令与文件声明的芯片不一致")
                synth.write(data[pos] + (256 if command == 0x5F else 0), data[pos + 1])
                pos += 2
                continue
            if command == 0x64:
                if data[pos] not in waits:
                    raise ValueError("VGM 等待覆盖指令的目标必须为 0x62/0x63")
                waits[data[pos]] = struct.unpack_from("<H", data, pos + 1)[0]
                pos += 3
                continue
            wait, = struct.unpack_from("<H", data, pos)
            pos += 2
        elif command in waits:
            wait = waits[command]
        elif 0x70 <= command <= 0x7F:
            wait = (command & 15) + 1
        elif command == 0x67:
            if pos + 6 > len(data) or data[pos] != 0x66:
                raise ValueError(f"VGM 数据块格式错误，位置 0x{command_pos:X}")
            size, = struct.unpack_from("<I", data, pos + 2)
            pos += 6 + (size & 0x7FFFFFFF)
            if pos > len(data):
                raise ValueError("VGM 数据块长度超出文件范围")
            continue
        else:
            raise ValueError(f"暂不支持 VGM 指令 0x{command:02X}，位置 0x{command_pos:X}；仅转换 OPL2/OPL3 2-op 音乐")
        if wait:
            synth.flush()
            synth.tick += wait
    if not ended:
        raise ValueError("VGM 缺少结束指令 0x66")
    if progress is not None and progress(1.0) is False:
        raise ConversionCancelled()
    synth.finish(destination)
    return ConversionResult(source, destination, chip, synth.tick / SAMPLE_RATE,
                            synth.notes, synth.approximate_notes, synth.channel_approximations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "midi", help="VGM/VGZ 文件或目录")
    parser.add_argument("--output", type=Path, default=ROOT / "midi/converted", help="MIDI 输出目录")
    args = parser.parse_args()
    files = find_inputs(args.source)
    if not files:
        parser.error(f"没有 VGM/VGZ 文件：{args.source}")
    destinations = [relative for _, relative in files]
    if len(set(str(path).casefold() for path in destinations)) != len(destinations):
        parser.error("输入中存在同名 VGM/VGZ，转换后的 .mid 路径冲突")
    failed = 0
    for index, (source, relative) in enumerate(files, 1):
        try:
            result = convert_file(source, args.output / relative)
            print(f"[{index}/{len(files)}] {relative}: {result.chip}, {result.duration:.3f}s, "
                  f"notes={result.notes}, approximate patches={result.approximate_notes}, "
                  f"channel approximations={result.channel_approximations}", flush=True)
        except (OSError, ValueError, EOFError, zlib.error) as error:
            failed += 1
            print(f"[{index}/{len(files)}] FAILED {source}: {error}", flush=True)
    print(f"Converted {len(files) - failed}/{len(files)} files", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
