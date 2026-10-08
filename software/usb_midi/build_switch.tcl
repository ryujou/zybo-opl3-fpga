set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root build/usb_midi]
file mkdir $out
cd $out
set_param general.maxThreads 2
open_checkpoint [file join $root fpga/build/post_syn.dcp]
set ps [get_cells -hier -filter {REF_NAME == PS7}]
set gpio [get_pins $ps/EMIOGPIOI\[0\]]
set old_net [get_nets -of_objects $gpio]
disconnect_net -net $old_net -objects $gpio
create_port -direction IN sw0
set_property PACKAGE_PIN G15 [get_ports sw0]
set_property IOSTANDARD LVCMOS33 [get_ports sw0]
create_cell -reference IBUF mode_switch_ibuf
create_cell -reference FDRE mode_switch_meta
create_cell -reference FDRE mode_switch_sync
set_property ASYNC_REG true [get_cells {mode_switch_meta mode_switch_sync}]
set_property INIT 1'b0 [get_cells {mode_switch_meta mode_switch_sync}]
set clk [get_nets design_1_i/processing_system7_0_FCLK_CLK0]
if {[llength $clk] != 1} {error "Missing buffered PS FCLK0"}
set zero [get_nets $old_net]
set one [get_nets -hier -filter {NAME =~ "*<const1>"}]
set one [lindex $one 0]
foreach {net objects} {
    mode_switch_pin {sw0 mode_switch_ibuf/I}
    mode_switch_raw {mode_switch_ibuf/O mode_switch_meta/D}
    mode_switch_stage {mode_switch_meta/Q mode_switch_sync/D}
    mode_switch_level {mode_switch_sync/Q}
} {
    create_net $net
    foreach object $objects {
        if {$object == "sw0"} {connect_net -net [get_nets $net] -objects [get_ports $object]} else {connect_net -net [get_nets $net] -objects [get_pins $object]}
    }
}
connect_net -hier -net [get_nets mode_switch_level] -objects $gpio
connect_net -hier -net $clk -objects [get_pins {mode_switch_meta/C mode_switch_sync/C}]
connect_net -hier -net $zero -objects [get_pins {mode_switch_meta/R mode_switch_sync/R}]
connect_net -hier -net [get_nets $one] -objects [get_pins {mode_switch_meta/CE mode_switch_sync/CE}]
set_false_path -from [get_ports sw0] -to [get_pins mode_switch_meta/D]
opt_design
place_design
route_design
report_timing_summary -file [file join $out dual_timing.txt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] < 0} {error "Dual-mode design has negative setup slack"}
write_checkpoint -force [file join $out opl3_dual.dcp]
write_bitstream -force [file join $out opl3_dual.bit]
exit
