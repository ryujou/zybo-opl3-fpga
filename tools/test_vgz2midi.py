# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused protocol and MIDI tests: python -B tools/test_vgz2midi.py."""
import gzip
from pathlib import Path
import struct
import tempfile
import unittest

import mido

from vgz2midi import (ConversionCancelled, MELODIC_CHANNELS, OplToMidi,
                      OPERATOR_OFFSETS, PATCHES, PATCH_KEYS, _match_patch,
                      convert_file, find_inputs)


def setup_voice(synth, voice=0, program=0, fnum=580, block=4, pan=0x30):
    patch = next(p for p in PATCHES if not p["drum"] and p["program"] == program)
    bank, channel = divmod(voice, 9)
    base = bank * 256
    synth.write(1, 32)
    if synth.chip == "OPL3":
        synth.write(0x105, 1)
    for offset, operator in zip((0, 3), patch["operators"]):
        for register, value in zip((0x20, 0x40, 0x60, 0x80, 0xE0), operator):
            synth.write(base + register + OPERATOR_OFFSETS[channel] + offset, value)
    synth.write(base + 0xC0 + channel, patch["feedback"] | pan)
    synth.write(base + 0xA0 + channel, fnum & 255)
    synth.write(base + 0xB0 + channel, 32 | block << 2 | fnum >> 8)


def vgm(commands, opl3=False):
    header = bytearray(0x100)
    header[:4] = b"Vgm "
    struct.pack_into("<I", header, 4, len(header) + len(commands) - 4)
    struct.pack_into("<I", header, 8, 0x171)
    struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", header, 0x5C if opl3 else 0x50, 14318180 if opl3 else 3579545)
    return bytes(header) + commands


def check_balanced(test, track):
    active = set()
    for message in track:
        test.assertGreaterEqual(message.time, 0)
        if message.type == "note_on" and message.velocity:
            key = (message.channel, message.note)
            test.assertNotIn(key, active)
            active.add(key)
        elif message.type == "note_off":
            key = (message.channel, message.note)
            test.assertIn(key, active)
            active.remove(key)
    test.assertFalse(active)


class ConverterTests(unittest.TestCase):
    def test_bank58_patch_lookup(self):
        for index, key in enumerate(PATCH_KEYS):
            matched, approximate = _match_patch(key)
            self.assertFalse(approximate)
            self.assertEqual(PATCH_KEYS[matched], key)

    def test_pitch_volume_pan_without_retrigger(self):
        synth = OplToMidi("OPL3", 14318180, "test")
        setup_voice(synth, pan=0x10)
        synth.flush()
        notes = [m for m in synth.track if m.type == "note_on"]
        self.assertEqual(notes[0].note, 69)  # FNUM 580, block 4 ≈ A4.
        synth.tick = 4410
        synth.write(0xA0, 590 & 255)
        synth.write(0xB0, 32 | 4 << 2 | 590 >> 8)
        synth.write(0x43, 30)
        synth.write(0xC0, PATCHES[0]["feedback"] | 0x20)
        synth.flush()
        self.assertEqual(sum(m.type == "note_on" for m in synth.track), 1)
        self.assertTrue(any(m.type == "pitchwheel" and m.pitch > 0 for m in synth.track))
        self.assertTrue(any(m.type == "control_change" and m.control == 7 and m.value < 127 for m in synth.track))
        self.assertTrue(any(m.type == "control_change" and m.control == 10 and m.value == 127 for m in synth.track))

    def test_same_tick_gate_edges_and_shared_unison(self):
        synth = OplToMidi("OPL3", 14318180, "test")
        setup_voice(synth, 0)
        setup_voice(synth, 9)
        synth.flush()
        self.assertEqual(synth.notes, 1)
        synth.tick = 10
        synth.write(0xB0, 4 << 2 | 580 >> 8)
        self.assertFalse(any(m.type == "note_off" for m in synth.track))
        synth.write(0x1B0, 4 << 2 | 580 >> 8)
        synth.write(0xB0, 32 | 4 << 2 | 580 >> 8)
        synth.write(0xB0, 4 << 2 | 580 >> 8)
        check_balanced(self, synth.track)
        self.assertEqual(synth.notes, 2)

    def test_18_voices_and_channel_limit(self):
        synth = OplToMidi("OPL3", 14318180, "test")
        for voice in range(18):
            setup_voice(synth, voice, program=voice, fnum=500 + voice * 5)
        synth.flush()
        self.assertEqual(len([a for a in synth.active if a is not None]), 18)
        self.assertGreater(synth.channel_approximations, 0)
        self.assertTrue(all(a[0] in MELODIC_CHANNELS for a in synth.active if a is not None))
        for voice in range(18):
            synth.release(voice)
        check_balanced(self, synth.track)

    def test_rhythm_drums(self):
        synth = OplToMidi("OPL2", 3579545, "test")
        synth.write(0xBD, 0x3F)
        synth.flush()
        drums = [m for m in synth.track if m.type == "note_on"]
        self.assertEqual({m.note for m in drums}, {35, 38, 45, 49, 42})
        self.assertTrue(all(m.channel == 9 for m in drums))
        synth.tick = 735
        synth.write(0xBD, 32)
        synth.flush()
        check_balanced(self, synth.track)

    def test_sample_timing_gzip_unicode_and_cancellation(self):
        commands = bytes((0x5A, 0xA0, 68, 0x5A, 0xB0, 50,
                          0x64, 0x62, 100, 0, 0x62, 0x70, 0x61, 25, 0,
                          0x5A, 0xB0, 18, 0x66))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "中文曲目.VGZ"
            destination = Path(directory) / "输出/曲目.mid"
            source.write_bytes(gzip.compress(vgm(commands)))
            result = convert_file(source, destination)
            midi = mido.MidiFile(destination, charset="utf-8")
            self.assertAlmostEqual(result.duration, 126 / 44100)
            self.assertAlmostEqual(midi.length, result.duration)
            check_balanced(self, midi.tracks[0])
            self.assertEqual(find_inputs(source)[0][1].name, "中文曲目.mid")
            cancelled = Path(directory) / "cancelled.mid"
            with self.assertRaises(ConversionCancelled):
                convert_file(source, cancelled, lambda _: False)
            self.assertFalse(cancelled.exists())

    def test_invalid_and_unsupported_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "test.vgm", Path(directory) / "test.mid"
            for payload, message in ((b"bad", "有效"),
                                     (vgm(bytes((0x5A,))), "数据不足"),
                                     (vgm(bytes((0x5F, 4, 1, 0x66)), True), "4-op"),
                                     (vgm(bytes((0x52, 0, 0, 0x66))), "0x52"),
                                     (vgm(bytes((0x70,))), "结束指令")):
                source.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, message):
                    convert_file(source, output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
