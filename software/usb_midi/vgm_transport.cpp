#include "transport.h"
#include "usb_device.h"

int transport_open_stream() { return XST_SUCCESS; }
void transport_close_stream() {}
bool transport_read_byte(u8 *value) { return vgm_usb_read(value); }
void transport_write(const u8 *data, size_t length) { vgm_usb_write(data, length); }
const TransportCapabilities &transport_get_capabilities() {
    static const TransportCapabilities caps = {TransportKind::Usb, 0, 0, 1024, 1024, 1, false};
    return caps;
}
