set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root build/usb_midi/ila]
file mkdir $out
cd $out
set_param general.maxThreads 2
open_checkpoint [file join $root fpga/build/post_syn.dcp]
set i2s_nets [get_nets {i2s_sclk_OBUF i2s_ws_OBUF i2s_sd_OBUF}]
set_property IOB false [get_ports {i2s_sclk i2s_ws i2s_sd}]
set i2s_drivers [get_cells -of_objects [get_pins -leaf -of_objects $i2s_nets -filter {DIRECTION == OUT}]]
set_property IOB false $i2s_drivers
# The original SCLK output uses the I/O flip-flop's D inversion. A fabric
# flip-flop needs an explicit inverter when its output is also routed to ILA.
set sclk_ff [get_cells design_1_i/opl3_fpga_0/inst/i2s/i2s_sclk_reg]
set sclk_d [get_pins $sclk_ff/D]
set sclk_source [get_nets -of_objects $sclk_d]
disconnect_net -net $sclk_source -objects $sclk_d
create_cell -reference LUT1 debug_i2s_sclk_invert
set_property INIT 2'h1 [get_cells debug_i2s_sclk_invert]
connect_net -hier -net $sclk_source -objects [get_pins debug_i2s_sclk_invert/I0]
create_net debug_i2s_sclk_d
connect_net -hier -net [get_nets debug_i2s_sclk_d] -objects [get_pins {debug_i2s_sclk_invert/O design_1_i/opl3_fpga_0/inst/i2s/i2s_sclk_reg/D}]
set_property IS_D_INVERTED 1'b0 $sclk_ff
create_debug_core ila_usb_midi ila
set_property C_DATA_DEPTH 8192 [get_debug_cores ila_usb_midi]
set_property C_EN_STRG_QUAL true [get_debug_cores ila_usb_midi]
set_property ALL_PROBE_SAME_MU_CNT 2 [get_debug_cores ila_usb_midi]
set_property C_INPUT_PIPE_STAGES 1 [get_debug_cores ila_usb_midi]
set_property port_width 1 [get_debug_ports ila_usb_midi/clk]
connect_debug_port ila_usb_midi/clk [get_nets ac_mclk_OBUF]
set_property port_width 1 [get_debug_ports ila_usb_midi/probe0]
connect_debug_port ila_usb_midi/probe0 [get_nets design_1_i/opl3_fpga_0/inst/sample_valid]
foreach {port channel} {probe1 l probe2 r} {
    create_debug_port ila_usb_midi probe
    set_property port_width 16 [get_debug_ports ila_usb_midi/$port]
    set nets {}
    # PCM is signed 16-bit, shifted left five places in the 24-bit DAC word.
    foreach bit {5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 22} {
        lappend nets [get_nets [format {design_1_i/opl3_fpga_0/inst/sample_%s[%d]} $channel $bit]]
    }
    connect_debug_port ila_usb_midi/$port $nets
}
create_debug_port ila_usb_midi probe
set_property port_width 3 [get_debug_ports ila_usb_midi/probe3]
connect_debug_port ila_usb_midi/probe3 $i2s_nets
implement_debug_core
opt_design
write_checkpoint -force [file join $out debug_opt.dcp]
place_design
route_design
report_timing_summary -file [file join $out timing.txt]
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] < 0} {
    error "ILA design has negative setup slack"
}
write_debug_probes -force [file join $out opl3_midi.ltx]
write_checkpoint -force [file join $out opl3_midi.dcp]
write_bitstream -force [file join $out opl3_midi.bit]
exit
