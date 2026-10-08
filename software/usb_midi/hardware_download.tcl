set root [file normalize [file join [file dirname [info script]] ../..]]
set bitfile [file join $root fpga/build/opl3.bit]
if {[llength $argv]} { set bitfile [file normalize [lindex $argv 0]] }
set elffile [file join $root build/usb_midi/opl3_usb_midi.elf]
set vitis J:/FPGA/2025.2/Vitis
if {[info exists env(XILINX_VITIS)]} { set vitis $env(XILINX_VITIS) }
set nm [file join $vitis gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-nm.exe]

if {[catch {
    connect -url tcp:localhost:3121
    targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
    stop
    # Reset PS peripherals and caches before loading a replacement standalone image.
    rst -system
    after 500
    targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
    stop
    source [file join $root vitis_project/opl3_platform/export/opl3_platform/hw/sdt/ps7_init.tcl]
    ps7_init
    targets -set -nocase -filter {name =~ "*xc7z010*"}
    fpga -file $bitfile
    targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
    ps7_post_config
    dow $elffile
    set symbols [exec $nm --defined-only $elffile]
    foreach name {_stack_end __stack} {
        if {![regexp -line [format {^([0-9a-fA-F]+) B %s$} $name] $symbols -> address]} { error "Missing $name symbol" }
        set stack($name) 0x$address
    }
    # Fill only the new ELF's main stack while its CPU is stopped, for a JTAG high-water measurement.
    mwr -force $stack(_stack_end) 0xa55aa55a [expr {($stack(__stack) - $stack(_stack_end)) / 4}]
    con
    puts "Downloaded $elffile with $bitfile"
    disconnect
} failure]} {
    puts stderr $failure
    exit 1
}
exit
