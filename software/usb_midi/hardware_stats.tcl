set root [file normalize [file join [file dirname [info script]] ../..]]
set vitis J:/FPGA/2025.2/Vitis
if {[info exists env(XILINX_VITIS)]} { set vitis $env(XILINX_VITIS) }
set nm [file join $vitis gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-nm.exe]
set symbols [exec $nm -C --defined-only [file join $root build/usb_midi/opl3_usb_midi.elf]]
foreach line [split $symbols \n] {
    if {[regexp {^([0-9a-fA-F]+) [A-Za-z] (.*)$} $line -> address name]} {
        set addresses($name) 0x$address
    }
}
connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
foreach name {
    midi_processed_events midi_max_dispatch_us midi_max_handler_us
    {(anonymous namespace)::received} {(anonymous namespace)::overflows}
    {(anonymous namespace)::malformed} {(anonymous namespace)::resets}
    midi_usb_setup_count midi_usb_ep0_tx_count midi_usb_send_errors
    __malloc_max_sbrked_mem
} {
    puts "$name = [mrd -force -value $addresses($name)]"
}
set name {(anonymous namespace)::configured}
puts "configured = [mrd -force -size b -value $addresses($name)]"
puts "PORTSC = [mrd -force -value 0xe0002184]"
set bottom $addresses(_stack_end)
set top $addresses(__stack)
set words [mrd -force -value $bottom [expr {($top - $bottom) / 4}]]
set untouched 0
foreach word $words {
    if {$word != 0xa55aa55a} { break }
    incr untouched 4
}
if {$untouched} {
    puts "main_stack_watermark_bytes = [expr {$top - $bottom - $untouched}]"
} else {
    puts "Main stack watermark is absent or exhausted"
}
disconnect
exit
