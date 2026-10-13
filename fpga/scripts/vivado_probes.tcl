set outputDir build

open_checkpoint $outputDir/post_route.dcp

set debugCores [get_debug_cores -quiet]
if { [llength $debugCores] > 0 } {
    write_debug_probes -force $outputDir/opl3.ltx
} else {
    set fh [open "$outputDir/opl3.ltx" w]
    puts $fh "# No debug cores present in this build."
    close $fh
}
