param(
    [string]$Bitstream = "fpga/build/opl3.bit",
    [string]$Elf = "vitis_project/imfplay_port/build/imfplay_port.elf",
    [string]$Xsct = "xsct"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& $Xsct (Join-Path $scriptDir "run_jtag.tcl") $Bitstream $Elf
