#ifndef OPL_HW_H_
#define OPL_HW_H_

#include "xil_types.h"

void opl_write_reg(u8 reg, u8 data, u8 bank);
void opl_reset_core(void);

#endif
