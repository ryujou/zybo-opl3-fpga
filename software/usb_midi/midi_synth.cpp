#include "midi_synth.h"
#include "adlmidi.h"
#include "adlmidi_midiplay.hpp"
#include <cstdio>

namespace {
ADL_MIDIPlayer *player = nullptr;
char init_error[160] = {};
}

bool midi_synth_init() {
    player = adl_init(49716);
    if (!player) {
        std::snprintf(init_error, sizeof(init_error), "%s", adl_errorString());
        return false;
    }
    if (adl_setNumChips(player, 1) != 0 || adl_setBank(player, 58) != 0) {
        std::snprintf(init_error, sizeof(init_error), "%s", adl_errorInfo(player));
        midi_synth_close();
        return false;
    }
    adl_setVolumeRangeModel(player, 0);
    adl_setSoftPanEnabled(player, 0);
    midi_synth_reset();
    return true;
}

const char *midi_synth_error() { return init_error; }

void midi_synth_close() {
    adl_close(player);
    player = nullptr;
}

void midi_synth_reset() {
    adl_panic(player);
    adl_rt_resetState(player);
    const uint8_t gm_reset[] = {0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7};
    adl_rt_systemExclusive(player, gm_reset, sizeof(gm_reset));
}

void midi_synth_tick(uint32_t elapsed_us) {
    static_cast<MIDIplay *>(player->adl_midiPlayer)->TickIterators(elapsed_us / 1000000.0);
}

void midi_synth_message(const uint8_t *data, size_t size) {
    const unsigned channel = data[0] & 15;
    (void)size; // MIDI packet parser has already checked each message length.
    switch (data[0] & 0xF0) {
    case 0x80: adl_rt_noteOff(player, channel, data[1]); break;
    case 0x90:
        if (data[2]) adl_rt_noteOn(player, channel, data[1], data[2]);
        else adl_rt_noteOff(player, channel, data[1]);
        break;
    case 0xA0: adl_rt_noteAfterTouch(player, channel, data[1], data[2]); break;
    case 0xB0: adl_rt_controllerChange(player, channel, data[1], data[2]); break;
    case 0xC0: adl_rt_patchChange(player, channel, data[1]); break;
    case 0xD0: adl_rt_channelAfterTouch(player, channel, data[1]); break;
    case 0xE0: adl_rt_pitchBend(player, channel, data[1] | (data[2] << 7)); break;
    default:
        if (data[0] == 0xFF) midi_synth_reset();
        break;
    }
}

void midi_synth_sysex(const uint8_t *data, size_t size) {
    adl_rt_systemExclusive(player, data, size);
}
