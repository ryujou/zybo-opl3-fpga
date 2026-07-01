connect -url tcp:localhost:3121
targets 2
stop
puts "STATE_BEGIN"
puts "g_active_transport"
puts [mrd 0x009A4890 1]
puts "g_configured"
puts [mrd 0x009B6FA4 1]
puts "g_debug_usb_ep0_setup_count"
puts [mrd 0x009A4900 1]
puts "g_debug_usb_ep0_rx_count"
puts [mrd 0x009A4904 1]
puts "g_debug_usb_ep1_out_count"
puts [mrd 0x009A4908 1]
puts "g_debug_usb_ep1_out_bytes"
puts [mrd 0x009A490C 1]
puts "g_debug_usb_ep1_in_count"
puts [mrd 0x009A4910 1]
puts "g_debug_usb_ep1_in_bytes"
puts [mrd 0x009A4914 1]
puts "g_debug_usb_last_event_type"
puts [mrd 0x009A4918 1]
puts "g_debug_usb_last_status"
puts [mrd 0x009A491C 1]
puts "g_debug_usb_open_stage"
puts [mrd 0x009A4920 1]
puts "g_debug_usb_open_error"
puts [mrd 0x009A4924 1]
puts "usb_mode"
puts [mrd 0xE00021A8 1]
puts "usb_otgsc"
puts [mrd 0xE00021A4 1]
puts "usb_portsc1"
puts [mrd 0xE0002184 1]
puts "usb_usbsts"
puts [mrd 0xE0002144 1]
puts "usb_usbintr"
puts [mrd 0xE0002148 1]
puts "usb_endptsetupstat"
puts [mrd 0xE00021AC 1]
puts "usb_endptprime"
puts [mrd 0xE00021B0 1]
puts "usb_endptstatus"
puts [mrd 0xE00021B8 1]
puts "STATE_END"
con
exit
