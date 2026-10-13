#include "timer_ps.h"
#include "xscutimer.h"
#include "sleep.h"

namespace { XScuTimer timer; }

int TimerInitialize(UINTPTR base) {
    XScuTimer_Config *config = XScuTimer_LookupConfig(base);
    if (!config) return XST_FAILURE;
    const int status = XScuTimer_CfgInitialize(&timer, config, config->BaseAddr);
    if (status != XST_SUCCESS) return status;
    XScuTimer_SetPrescaler(&timer, 0);
    // The SDT BSP starts its global timebase lazily on the first sleep call.
    usleep(1);
    return XST_SUCCESS;
}

void TimerDelay(u32 us) {
    XScuTimer_Stop(&timer);
    XScuTimer_DisableAutoReload(&timer);
    XScuTimer_LoadTimer(&timer, (TIMER_FREQ_HZ / 1000000) * us);
    XScuTimer_Start(&timer);
    while (XScuTimer_GetCounterValue(&timer)) {}
}
