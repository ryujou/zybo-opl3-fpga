#include "midi_parser.h"
#include "midi_synth.h"
#include "usb_descriptors.h"
#include "adlmidi.h"
#include "adlmidi_midiplay.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

struct Write { uint16_t address; uint8_t value; };
std::vector<Write> writes;
std::vector<std::vector<uint8_t>> messages, sysex_messages;
bool synth_enabled = false;
uint8_t registers[512] = {};

void midi_opl_write(uint16_t address, uint8_t value) {
    assert(address < 512);
    registers[address] = value;
    writes.push_back({address, value});
}
void midi_message_received(const uint8_t *data, size_t size) {
    messages.emplace_back(data, data + size);
    if (synth_enabled) midi_synth_message(data, size);
}
void midi_sysex_received(const uint8_t *data, size_t size) {
    sysex_messages.emplace_back(data, data + size);
    if (synth_enabled) midi_synth_sysex(data, size);
}
void packet(MidiParser &p, uint8_t cin, uint8_t a, uint8_t b = 0, uint8_t c = 0) {
    const uint8_t bytes[] = {cin, a, b, c};
    p.accept(bytes);
}
unsigned keys_on() {
    unsigned n = 0;
    for (unsigned bank = 0; bank < 2; ++bank)
        for (unsigned ch = 0; ch < 9; ++ch) n += !!(registers[bank * 256 + 0xB0 + ch] & 0x20);
    return n;
}

void test_descriptors() {
    assert(midi_device_descriptor[0] == 18 && midi_device_descriptor[7] == 64);
    assert(midi_device_descriptor[10] == 0x13 && midi_device_descriptor[11] == 0x40);
    const auto *d = midi_config_descriptor;
    assert((d[2] | d[3] << 8) == sizeof(midi_config_descriptor));
    unsigned interfaces = 0, endpoints = 0, jack_mask = 0;
    unsigned interface_no = 0, last_endpoint = 0;
    for (size_t i = 0; i < sizeof(midi_config_descriptor); i += d[i]) {
        assert(d[i] >= 2 && i + d[i] <= sizeof(midi_config_descriptor));
        if (d[i + 1] == 4) {
            ++interfaces;
            interface_no = d[i + 2];
            assert(d[i + 5] == 1);
            assert(d[i + 6] == (interface_no == 0 ? 1 : 3));
        } else if (d[i + 1] == 0x24 && interface_no == 1 && d[i + 2] >= 2) {
            jack_mask |= 1U << d[i + 4];
            if (d[i + 2] == 3) assert(d[i + 6] == (d[i + 4] == 3 ? 2 : 1));
        } else if (d[i + 1] == 5) {
            ++endpoints; last_endpoint = d[i + 2];
            assert(d[i + 3] == 2 && d[i + 4] == 64 && d[i + 5] == 0);
        } else if (d[i + 1] == 0x25) {
            assert(d[i + 3] == 1 && (jack_mask & (1U << d[i + 4])));
            assert(d[i + 4] == (last_endpoint == 1 ? 1 : 3));
        }
    }
    assert(interfaces == 2 && endpoints == 2 && jack_mask == 0x1E);
    uint8_t text[128];
    assert(midi_string_descriptor(0, text) == 4);
    assert(midi_string_descriptor(2, text) == 30);
    assert(midi_string_descriptor(0xEE, text) == 0);
    std::puts("PASS descriptors: AC/MS topology, endpoint/jack links, strings, no WCID");
}

void test_parser() {
    MidiParser p;
    packet(p, 9, 0x90, 60, 100);
    packet(p, 0xC, 0xC0, 12);
    packet(p, 0xE, 0xE0, 0, 64);
    assert(messages.size() == 3 && messages[1].size() == 2);
    packet(p, 0x19, 0x90, 60, 1); // Unsupported cable
    packet(p, 9, 0x80, 60, 1); // CIN/status mismatch
    packet(p, 9, 0x90, 0xFF, 1);
    assert(messages.size() == 3 && p.invalid_packets == 3);
    packet(p, 4, 0xF0, 0x7E, 0x7F);
    packet(p, 0xF, 0xF8); // Realtime message does not interrupt SysEx
    packet(p, 7, 9, 1, 0xF7);
    assert(sysex_messages.size() == 1 && sysex_messages[0].size() == 6);
    packet(p, 4, 0xF0, 1, 2);
    for (int i = 0; i < 350; ++i) packet(p, 4, 1, 2, 3);
    packet(p, 5, 0xF7);
    assert(p.oversized_sysex == 1 && sysex_messages.size() == 1);
    packet(p, 6, 0xF0, 0xF7);
    assert(sysex_messages.size() == 2);
    packet(p, 4, 0xF0, 1, 2);
    p.reset();
    packet(p, 5, 0xF7);
    assert(sysex_messages.size() == 2);
    packet(p, 4, 0xF0, 1, 2);
    packet(p, 0xF, 0xFF);
    packet(p, 5, 0xF7);
    assert(sysex_messages.size() == 2);
    packet(p, 4, 0xF0, 1, 2);
    packet(p, 7, 3, 0x90, 0xF7);
    packet(p, 6, 0xF0, 0xF7);
    assert(sysex_messages.size() == 3);
    const uint8_t transfer[] = {9, 0x90, 64, 90, 8, 0x80, 64, 0};
    const size_t before = messages.size();
    for (size_t i = 0; i < sizeof(transfer); i += 4) p.accept(transfer + i);
    assert(messages.size() == before + 2);
    const size_t raw_before = messages.size();
    for (const uint8_t byte : {0x90, 60, 100, 61, 0, 0xF8, 0xC0, 12}) packet(p, 0xF, byte);
    assert(messages.size() == raw_before + 4);
    assert(messages[raw_before + 1] == std::vector<uint8_t>({0x90, 61, 0}));
    for (const uint8_t byte : {0xF0, 0x7E, 0x7F, 9, 1, 0xF7}) packet(p, 0xF, byte);
    assert(sysex_messages.back() == std::vector<uint8_t>({0xF0, 0x7E, 0x7F, 9, 1, 0xF7}));
    std::puts("PASS MIDI parser: messages, cable/CIN validation, multi-event transfers, fragmented/oversized SysEx");
}

void test_synth() {
    synth_enabled = true;
    assert(midi_synth_init());
    assert((registers[0x105] & 1) && keys_on() == 0);
    MidiParser p;
    packet(p, 9, 0x90, 60, 100);
    assert(keys_on() > 0);
    packet(p, 9, 0x90, 60, 0);
    assert(keys_on() == 0);
    packet(p, 0xB, 0xB0, 64, 127);
    packet(p, 9, 0x90, 60, 100);
    packet(p, 8, 0x80, 60, 0);
    assert(keys_on() > 0);
    packet(p, 0xB, 0xB0, 64, 0);
    assert(keys_on() == 0);
    packet(p, 9, 0x90, 60, 100);
    auto before = writes.size();
    packet(p, 0xE, 0xE0, 127, 127);
    bool changed_pitch = false;
    for (size_t i = before; i < writes.size(); ++i)
        changed_pitch |= (writes[i].address & 0xF0) == 0xA0;
    assert(changed_pitch);
    packet(p, 0xB, 0xB0, 10, 0);
    bool left = false;
    for (unsigned bank = 0; bank < 2; ++bank)
        for (unsigned ch = 0; ch < 9; ++ch)
            if (registers[bank * 256 + 0xB0 + ch] & 0x20)
                left |= (registers[bank * 256 + 0xC0 + ch] & 0x30) == 0x10;
    assert(left);
    packet(p, 0xB, 0xB0, 120, 0);
    assert(keys_on() == 0);
    midi_synth_reset();
    packet(p, 9, 0x99, 36, 100);
    packet(p, 8, 0x89, 36, 0);
    assert(keys_on() > 0); // The library extends short percussion notes.
    midi_synth_tick(100000);
    assert(keys_on() == 0); // Must expire even when no further MIDI arrives.
    std::array<uint8_t, 512> first_patch;
    bool different_patch = false;
    for (unsigned program = 0; program < 128; ++program) {
        midi_synth_reset();
        packet(p, 0xC, 0xC0, program);
        packet(p, 9, 0x90, 60, 100);
        assert(keys_on() > 0);
        if (!program) std::memcpy(first_patch.data(), registers, sizeof(registers));
        else different_patch |= std::memcmp(first_patch.data(), registers, sizeof(registers)) != 0;
        midi_synth_tick(100000);
        packet(p, 8, 0x80, 60, 0);
    }
    assert(different_patch);
    midi_synth_reset();
    for (unsigned ch = 0; ch < 16; ++ch) {
        packet(p, 9, 0x90 | ch, ch == 9 ? 36 : 60 + ch, 100);
        midi_synth_tick(1000);
    }
    for (unsigned key = 36; key < 96; ++key) packet(p, 9, 0x90, key, 90);
    assert(keys_on() > 0 && keys_on() <= 18);
    packet(p, 4, 0xF0, 0x7E, 0x7F);
    packet(p, 7, 9, 1, 0xF7);
    assert(keys_on() == 0);
    midi_synth_close();
    synth_enabled = false;
    std::puts("PASS bank 58 synth: 128 programs, 16 channels/drums, note off, sustain, pitch, pan, voice stealing, GM reset, idle time progression");
}

void test_reference() {
    assert(midi_synth_init());
    writes.clear();
    synth_enabled = true;
    MidiParser p;
    packet(p, 0xC, 0xC2, 30);
    packet(p, 9, 0x92, 64, 96);
    packet(p, 0xB, 0xB2, 7, 70);
    packet(p, 0xB, 0xB2, 11, 60);
    packet(p, 0xB, 0xB2, 10, 127);
    packet(p, 0xE, 0xE2, 0, 80);
    packet(p, 0xA, 0xA2, 64, 72);
    packet(p, 0xD, 0xD2, 83);
    midi_synth_tick(27000);
    packet(p, 0xB, 0xB2, 123, 0);
    assert(keys_on() == 0);
    const auto actual = writes;
    midi_synth_close();
    synth_enabled = false;

    ADL_MIDIPlayer *reference = adl_init(49716);
    assert(reference && adl_setNumChips(reference, 1) == 0 && adl_setBank(reference, 58) == 0);
    adl_setVolumeRangeModel(reference, 0);
    adl_setSoftPanEnabled(reference, 0);
    adl_panic(reference);
    adl_rt_resetState(reference);
    const uint8_t gm[] = {0xF0, 0x7E, 0x7F, 9, 1, 0xF7};
    adl_rt_systemExclusive(reference, gm, sizeof(gm));
    writes.clear();
    adl_rt_patchChange(reference, 2, 30);
    adl_rt_noteOn(reference, 2, 64, 96);
    adl_rt_controllerChange(reference, 2, 7, 70);
    adl_rt_controllerChange(reference, 2, 11, 60);
    adl_rt_controllerChange(reference, 2, 10, 127);
    adl_rt_pitchBend(reference, 2, 10240);
    adl_rt_noteAfterTouch(reference, 2, 64, 72);
    adl_rt_channelAfterTouch(reference, 2, 83);
    static_cast<MIDIplay *>(reference->adl_midiPlayer)->TickIterators(0.027);
    adl_rt_controllerChange(reference, 2, 123, 0);
    assert(actual.size() == writes.size());
    for (size_t i = 0; i < actual.size(); ++i)
        assert(actual[i].address == writes[i].address && actual[i].value == writes[i].value);
    adl_close(reference);
    std::puts("PASS register trace matches direct pinned-library API: bank 58, volume/expression, hardware pan, bend, aftertouch, all notes off, tick");
}

int main() {
    test_descriptors();
    test_parser();
    test_synth();
    test_reference();
    std::puts("All USB-MIDI host tests passed.");
}
