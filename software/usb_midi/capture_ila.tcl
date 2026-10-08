set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root build/usb_midi/ila]
set label capture
set mode samples
if {[llength $argv]} { set label [lindex $argv 0] }
if {[llength $argv] > 1} { set mode [lindex $argv 1] }
open_hw_manager
connect_hw_server -url localhost:3121
set target [get_hw_targets *210279540276*]
if {[llength $target] != 1} { error "Expected Zybo JTAG serial 210279540276" }
current_hw_target $target
set_property PARAM.FREQUENCY 2000000 $target
open_hw_target
set device [get_hw_devices xc7z010*]
if {[llength $device] != 1} { error "Expected one XC7Z010" }
current_hw_device $device
set_property PROBES.FILE [file join $out opl3_midi.ltx] $device
refresh_hw_device $device
set ila [get_hw_ilas -of_objects $device]
if {[llength $ila] != 1} { error "Expected USB-MIDI ILA test image" }
set_property CONTROL.TRIGGER_POSITION 0 $ila
set_property CONTROL.DATA_DEPTH 8192 $ila
set_property CONTROL.WINDOW_COUNT 1 $ila
set valid [get_hw_probes -of_objects $ila *sample_valid*]
if {[llength $valid] != 1} { error "Expected sample_valid probe" }
set_property TRIGGER_COMPARE_VALUE eq1'b1 $valid
if {$mode == "samples"} {
    set_property CONTROL.CAPTURE_MODE BASIC $ila
    set_property CAPTURE_COMPARE_VALUE eq1'b1 $valid
} elseif {$mode == "i2s"} {
    set_property CONTROL.CAPTURE_MODE ALWAYS $ila
} else { error "Capture mode must be samples or i2s" }
run_hw_ila $ila
after 1000
wait_on_hw_ila -timeout 0.17 $ila
set data [upload_hw_ila_data $ila]
write_hw_ila_data -force -csv_file [file join $out $label.csv] $data
close_hw_target
disconnect_hw_server
close_hw_manager
exit
