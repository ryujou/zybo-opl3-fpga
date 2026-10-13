#include "opl_hw.h"

#include "xil_io.h"
#include "xparameters.h"

void opl_write_reg(u8 reg, u8 data, u8 bank)
{
	int address = bank ? 0x2 : 0x0;

	Xil_Out8(XPAR_OPL3_FPGA_0_BASEADDR + address, reg);
	for (int i = 0; i < 6; ++i) {
		Xil_In8(XPAR_OPL3_FPGA_0_BASEADDR);
	}

	Xil_Out8(XPAR_OPL3_FPGA_0_BASEADDR + 0x1, data);
	for (int i = 0; i < 24; ++i) {
		Xil_In8(XPAR_OPL3_FPGA_0_BASEADDR);
	}
}

void opl_reset_core(void)
{
	for (int i = 0; i < 256; ++i) {
		opl_write_reg(static_cast<u8>(i), 0, 0);
		opl_write_reg(static_cast<u8>(i), 0, 1);
	}

	// Enable OPL3 mode and unmute audio output.
	opl_write_reg(0x05, 0x01, 1);
	opl_write_reg(0x02, 0x01, 1);
}
