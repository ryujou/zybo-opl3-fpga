from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

from mido import Message

from gm_mapper import OplPatch, patch_for_drum, patch_for_program
from protocol import OplWrite


OPERATOR_BASE = [0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12]


@dataclass
class ChannelState:
    program: int = 0
    volume: int = 100
    expression: int = 127
    pan: int = 64
    sustain: bool = False
    pitch_bend: int = 0


@dataclass
class VoiceState:
    slot: int
    midi_channel: int
    midi_note: int
    velocity: int
    patch: OplPatch
    start_order: int
    key_on: bool = True
    sustained: bool = False


@dataclass
class SynthSnapshot:
    channels: List[ChannelState]
    voices: List[Optional[VoiceState]]
    order_counter: int


class OplMidiSynth:
    def __init__(self) -> None:
        self.channels = [ChannelState() for _ in range(16)]
        self.voices: List[Optional[VoiceState]] = [None for _ in range(18)]
        self.order_counter = 0
        self.note_to_slot: Dict[Tuple[int, int], int] = {}

    def clone_snapshot(self) -> SynthSnapshot:
        return SynthSnapshot(
            channels=deepcopy(self.channels),
            voices=deepcopy(self.voices),
            order_counter=self.order_counter,
        )

    def restore_snapshot(self, snapshot: SynthSnapshot) -> None:
        self.channels = deepcopy(snapshot.channels)
        self.voices = deepcopy(snapshot.voices)
        self.order_counter = snapshot.order_counter
        self.note_to_slot = {}
        for slot, voice in enumerate(self.voices):
            if voice is not None:
                self.note_to_slot[(voice.midi_channel, voice.midi_note)] = slot

    def render_restore_writes(self) -> List[OplWrite]:
        writes: List[OplWrite] = []
        for slot, voice in enumerate(self.voices):
            if voice is None:
                continue
            channel_state = self.channels[voice.midi_channel]
            writes.extend(self._voice_patch_writes(slot, voice.patch, channel_state, voice.velocity))
            writes.extend(self._voice_frequency_writes(slot, voice.midi_note, channel_state.pitch_bend, key_on=True))
        return writes

    def all_notes_off_writes(self) -> List[OplWrite]:
        writes: List[OplWrite] = []
        for slot, voice in enumerate(self.voices):
            if voice is not None and voice.key_on:
                writes.extend(self._voice_key_off_writes(slot))
                voice.key_on = False
                voice.sustained = False
        return writes

    def handle_message(self, message: Message) -> List[OplWrite]:
        msg_type = message.type
        if msg_type == "program_change":
            self.channels[message.channel].program = message.program
            return []
        if msg_type == "control_change":
            return self._handle_control_change(message)
        if msg_type == "pitchwheel":
            return self._handle_pitch(message.channel, message.pitch)
        if msg_type == "note_on":
            if message.velocity == 0:
                return self._handle_note_off(message.channel, message.note)
            return self._handle_note_on(message.channel, message.note, message.velocity)
        if msg_type == "note_off":
            return self._handle_note_off(message.channel, message.note)
        return []

    def _handle_control_change(self, message: Message) -> List[OplWrite]:
        state = self.channels[message.channel]
        control = message.control
        value = message.value
        if control == 7:
            state.volume = value
            return self._rewrite_channel_levels(message.channel)
        if control == 10:
            state.pan = value
            return self._rewrite_channel_levels(message.channel)
        if control == 11:
            state.expression = value
            return self._rewrite_channel_levels(message.channel)
        if control == 64:
            was_sustain = state.sustain
            state.sustain = value >= 64
            if was_sustain and not state.sustain:
                return self._release_sustained_notes(message.channel)
            return []
        if control in (120, 123):
            return self._channel_all_notes_off(message.channel)
        if control == 121:
            state.volume = 100
            state.expression = 127
            state.pan = 64
            state.pitch_bend = 0
            state.sustain = False
            return self._rewrite_channel_levels(message.channel)
        return []

    def _handle_pitch(self, channel: int, pitch: int) -> List[OplWrite]:
        self.channels[channel].pitch_bend = pitch
        writes: List[OplWrite] = []
        for slot, voice in enumerate(self.voices):
            if voice is not None and voice.midi_channel == channel and voice.key_on:
                writes.extend(self._voice_frequency_writes(slot, voice.midi_note, pitch, key_on=True))
        return writes

    def _handle_note_on(self, channel: int, note: int, velocity: int) -> List[OplWrite]:
        writes: List[OplWrite] = []
        existing_slot = self.note_to_slot.get((channel, note))
        if existing_slot is not None:
            writes.extend(self._release_voice(existing_slot))

        slot = self._allocate_slot()
        if slot is None:
            slot = self._steal_slot()
            if slot is None:
                return writes
            writes.extend(self._release_voice(slot))

        state = self.channels[channel]
        patch = patch_for_drum(note) if channel == 9 else patch_for_program(state.program)
        self.order_counter += 1
        voice = VoiceState(
            slot=slot,
            midi_channel=channel,
            midi_note=note,
            velocity=velocity,
            patch=patch,
            start_order=self.order_counter,
        )
        self.voices[slot] = voice
        self.note_to_slot[(channel, note)] = slot

        writes.extend(self._voice_patch_writes(slot, patch, state, velocity))
        writes.extend(self._voice_frequency_writes(slot, note, state.pitch_bend, key_on=True))
        return writes

    def _handle_note_off(self, channel: int, note: int) -> List[OplWrite]:
        slot = self.note_to_slot.get((channel, note))
        if slot is None:
            return []

        voice = self.voices[slot]
        if voice is None:
            return []

        if self.channels[channel].sustain:
            voice.sustained = True
            voice.key_on = False
            return []

        return self._release_voice(slot)

    def _release_sustained_notes(self, channel: int) -> List[OplWrite]:
        writes: List[OplWrite] = []
        for slot, voice in enumerate(self.voices):
            if voice is not None and voice.midi_channel == channel and voice.sustained:
                writes.extend(self._release_voice(slot))
        return writes

    def _channel_all_notes_off(self, channel: int) -> List[OplWrite]:
        writes: List[OplWrite] = []
        for slot, voice in enumerate(self.voices):
            if voice is not None and voice.midi_channel == channel:
                writes.extend(self._release_voice(slot))
        return writes

    def _rewrite_channel_levels(self, channel: int) -> List[OplWrite]:
        writes: List[OplWrite] = []
        state = self.channels[channel]
        for slot, voice in enumerate(self.voices):
            if voice is not None and voice.midi_channel == channel:
                writes.extend(self._voice_patch_writes(slot, voice.patch, state, voice.velocity, only_levels=True))
        return writes

    def _release_voice(self, slot: int) -> List[OplWrite]:
        voice = self.voices[slot]
        if voice is None:
            return []
        self.note_to_slot.pop((voice.midi_channel, voice.midi_note), None)
        self.voices[slot] = None
        return self._voice_key_off_writes(slot)

    def _allocate_slot(self) -> Optional[int]:
        for idx, voice in enumerate(self.voices):
            if voice is None:
                return idx
        return None

    def _steal_slot(self) -> Optional[int]:
        best_slot = None
        best_voice = None
        for slot, voice in enumerate(self.voices):
            if voice is None:
                return slot
            if best_voice is None:
                best_slot = slot
                best_voice = voice
                continue
            if voice.sustained and not best_voice.sustained:
                best_slot = slot
                best_voice = voice
            elif voice.start_order < best_voice.start_order:
                best_slot = slot
                best_voice = voice
        return best_slot

    def _slot_to_bank_channel(self, slot: int) -> tuple[int, int]:
        if slot < 9:
            return 0, slot
        return 1, slot - 9

    def _voice_patch_writes(
        self,
        slot: int,
        patch: OplPatch,
        channel_state: ChannelState,
        velocity: int,
        *,
        only_levels: bool = False,
    ) -> List[OplWrite]:
        bank, channel = self._slot_to_bank_channel(slot)
        op_base = OPERATOR_BASE[channel]
        mod_offset = op_base
        car_offset = op_base + 3
        mod_level = self._apply_level(patch.mod_40, velocity, channel_state)
        car_level = self._apply_level(patch.car_40, velocity, channel_state)
        pan_bits = self._pan_bits(channel_state.pan)
        writes: List[OplWrite] = []
        if not only_levels:
            writes.extend(
                [
                    OplWrite(bank, 0x20 + mod_offset, patch.mod_20),
                    OplWrite(bank, 0x60 + mod_offset, patch.mod_60),
                    OplWrite(bank, 0x80 + mod_offset, patch.mod_80),
                    OplWrite(bank, 0xE0 + mod_offset, patch.mod_e0),
                    OplWrite(bank, 0x20 + car_offset, patch.car_20),
                    OplWrite(bank, 0x60 + car_offset, patch.car_60),
                    OplWrite(bank, 0x80 + car_offset, patch.car_80),
                    OplWrite(bank, 0xE0 + car_offset, patch.car_e0),
                ]
            )
        writes.extend(
            [
                OplWrite(bank, 0x40 + mod_offset, mod_level),
                OplWrite(bank, 0x40 + car_offset, car_level),
                OplWrite(bank, 0xC0 + channel, (patch.ch_c0 & 0x0F) | pan_bits),
            ]
        )
        return writes

    def _voice_frequency_writes(self, slot: int, midi_note: int, pitch_bend: int, *, key_on: bool) -> List[OplWrite]:
        bank, channel = self._slot_to_bank_channel(slot)
        frequency = self._note_frequency(midi_note, pitch_bend)
        fnum, block = self._frequency_to_fnum_block(frequency)
        b0 = ((block & 0x07) << 2) | ((fnum >> 8) & 0x03)
        if key_on:
            b0 |= 0x20
        return [
            OplWrite(bank, 0xA0 + channel, fnum & 0xFF),
            OplWrite(bank, 0xB0 + channel, b0),
        ]

    def _voice_key_off_writes(self, slot: int) -> List[OplWrite]:
        bank, channel = self._slot_to_bank_channel(slot)
        return [OplWrite(bank, 0xB0 + channel, 0x00)]

    def _note_frequency(self, midi_note: int, pitch_bend: int) -> float:
        semitones = pitch_bend / 8192.0 * 2.0
        return 440.0 * (2.0 ** (((midi_note - 69) + semitones) / 12.0))

    def _frequency_to_fnum_block(self, frequency: float) -> tuple[int, int]:
        best_block = 0
        best_fnum = 0
        for block in range(7, -1, -1):
            fnum = int(round(frequency * (2 ** 20) / (49_716.0 * (2 ** block))))
            if 0 < fnum < 1024:
                best_block = block
                best_fnum = fnum
                break
        best_fnum = max(1, min(1023, best_fnum))
        return best_fnum, best_block

    def _apply_level(self, base_reg: int, velocity: int, channel_state: ChannelState) -> int:
        base_tl = base_reg & 0x3F
        level = max(1, velocity) / 127.0
        level *= max(1, channel_state.volume) / 127.0
        level *= max(1, channel_state.expression) / 127.0
        attenuation = int(round((1.0 - level) * 48.0))
        final_tl = min(63, base_tl + attenuation)
        return (base_reg & 0xC0) | final_tl

    def _pan_bits(self, pan: int) -> int:
        if pan < 32:
            return 0x10
        if pan > 95:
            return 0x20
        return 0x30
