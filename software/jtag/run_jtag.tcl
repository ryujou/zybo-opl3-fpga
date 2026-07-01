if {[llength $argv] < 2} {
    puts "Usage: xsct run_jtag.tcl <bitstream> <elf>"
    exit 1
}

set bitfile [file normalize [lindex $argv 0]]
set elffile [file normalize [lindex $argv 1]]
set psinit [file normalize "vitis_project/opl3_platform/export/opl3_platform/hw/sdt/ps7_init.tcl"]

connect
source $psinit
targets -set -nocase -filter {name =~ "*xc7z010*"}
fpga -file $bitfile

targets -set -nocase -filter {name =~ "*APU*"}
stop
ps7_init
ps7_post_config

targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
rst -processor
dow $elffile
con
exit
