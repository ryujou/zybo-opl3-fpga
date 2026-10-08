connect -url tcp:localhost:3121
targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
set command [mrd -force -value 0xe0002140]
# Stopping the Zynq device controller removes its USB pull-up without halting ARM.
mwr -force 0xe0002140 [expr {$command & ~1}]
after 2000
mwr -force 0xe0002140 [expr {$command | 1}]
disconnect
exit
