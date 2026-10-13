#pragma once
#include "chips/opl_chip_base.h"

void midi_opl_write(uint16_t address, uint8_t value);

class FpgaOPL3 final : public OPLChipBaseT<FpgaOPL3> {
public:
    bool canRunAtPcmRate() const override { return true; }
    void nativePreGenerate() override {}
    void nativePostGenerate() override {}
    void nativeGenerate(int16_t *frame) override { frame[0] = frame[1] = 0; }
    void writeReg(uint16_t address, uint8_t value) override {
        midi_opl_write(address, value);
    }
    const char *emulatorName() override { return "Zybo OPL3 FPGA"; }
    ChipType chipType() override { return CHIPTYPE_OPL3; }
};
