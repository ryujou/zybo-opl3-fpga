#include "usb_descriptors.h"

const uint8_t midi_device_descriptor[18] = {
    18, 1, 0x00, 0x02, 0, 0, 0, 64,
    0xFE, 0xCA, 0x13, 0x40, 0x00, 0x01, 1, 2, 3, 1
};

const uint8_t midi_config_descriptor[101] = {
    9, 2, 101, 0, 2, 1, 0, 0xC0, 0,
    9, 4, 0, 0, 0, 1, 1, 0, 0,                 // AudioControl
    9, 0x24, 1, 0x00, 0x01, 9, 0, 1, 1,
    9, 4, 1, 0, 2, 1, 3, 0, 2,                 // MIDIStreaming
    7, 0x24, 1, 0x00, 0x01, 65, 0,
    6, 0x24, 2, 1, 1, 0,                       // Embedded IN jack 1
    6, 0x24, 2, 2, 2, 0,                       // External IN jack 2
    9, 0x24, 3, 1, 3, 1, 2, 1, 0,              // Embedded OUT jack 3
    9, 0x24, 3, 2, 4, 1, 1, 1, 0,              // External OUT jack 4
    9, 5, 0x01, 2, 64, 0, 0, 0, 0,
    5, 0x25, 1, 1, 1,
    9, 5, 0x81, 2, 64, 0, 0, 0, 0,
    5, 0x25, 1, 1, 3
};

size_t midi_string_descriptor(uint8_t index, uint8_t *output) {
    if (index == 0) {
        output[0] = 4; output[1] = 3; output[2] = 9; output[3] = 4;
        return 4;
    }
    static const char *strings[] = {"", "Ryujou", "Zybo OPL3 MIDI", "ZOPL3MIDI0001"};
    if (index >= 4) return 0;
    size_t n = 2;
    for (const char *p = strings[index]; *p; ++p) {
        output[n++] = static_cast<uint8_t>(*p);
        output[n++] = 0;
    }
    output[0] = static_cast<uint8_t>(n);
    output[1] = 3;
    return n;
}

const uint8_t vgm_device_descriptor[18] = {
    18, 1, 0, 2, 0, 0, 0, 64,
    0xFE, 0xCA, 0x12, 0x40, 0, 1, 1, 2, 3, 1
};
const uint8_t vgm_config_descriptor[32] = {
    9, 2, 32, 0, 1, 1, 0, 0xC0, 0,
    9, 4, 0, 0, 2, 0xFF, 0, 0, 0,
    7, 5, 0x01, 2, 64, 0, 0,
    7, 5, 0x81, 2, 64, 0, 0
};
const uint8_t vgm_ms_compat_descriptor[40] = {
    40, 0, 0, 0, 0, 1, 4, 0, 1, 0, 0, 0, 0, 0, 0, 0,
    0, 1, 'W', 'I', 'N', 'U', 'S', 'B', 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
};
size_t vgm_string_descriptor(uint8_t index, uint8_t *output) {
    if (index == 0) return midi_string_descriptor(0, output);
    if (index == 0xEE) {
        const uint8_t os[] = {18, 3, 'M', 0, 'S', 0, 'F', 0, 'T', 0,
                              '1', 0, '0', 0, '0', 0, 0x20, 0};
        for (size_t i = 0; i < sizeof(os); ++i) output[i] = os[i];
        return sizeof(os);
    }
    static const char *strings[] = {"", "Ryujou", "Zybo OPL3 USB Interface", "ZOPL3USB0001"};
    if (index >= 4) return 0;
    size_t n = 2;
    for (const char *p = strings[index]; *p; ++p) {
        output[n++] = static_cast<uint8_t>(*p); output[n++] = 0;
    }
    output[0] = static_cast<uint8_t>(n); output[1] = 3;
    return n;
}
