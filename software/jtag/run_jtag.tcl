if {[llength $argv] < 2} {
    puts "Usage: xsct run_jtag.tcl <bitstream> <elf>"
    exit 1
}

set bitfile [file normalize [lindex $argv 0]]
set elffile [file normalize [lindex $argv 1]]

connect
targets -set -nocase -filter {name =~ "*xc7z010*"}
fpga -file $bitfile

targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
rst -processor
dow $elffile
con
exit
