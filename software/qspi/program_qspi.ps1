param(
    [string]$Url = "tcp:localhost:3121",
    [string]$TargetName = "",
    [switch]$EraseAll,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

function Find-Tool {
    param([string]$ToolName)

    $cmd = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    if ($env:XILINX_VITIS) {
        $candidate = Join-Path $env:XILINX_VITIS ("bin/{0}.bat" -f $ToolName)
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw ("Tool not found: {0}. Add Vitis 2025.2 bin to PATH or set XILINX_VITIS." -f $ToolName)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$programFlash = Find-Tool "program_flash"
$bootBin = Join-Path $repoRoot "BOOT.bin"
$fsbl = Join-Path $repoRoot "vitis_project/opl3_platform/export/opl3_platform/sw/boot/fsbl.elf"

if (-not (Test-Path $bootBin)) {
    throw "BOOT.bin not found. Run software/qspi/build_boot.ps1 or make qspi-image first."
}

if (-not (Test-Path $fsbl)) {
    throw "fsbl.elf not found. Build the Vitis platform first."
}

$args = @(
    "-f", $bootBin,
    "-offset", "0",
    "-fsbl", $fsbl,
    "-flash_type", "qspi-x4-single",
    "-url", $Url
)

if ($EraseAll) {
    $args += "-erase_all"
}

if ($Verify) {
    $args += "-verify"
}

if ($TargetName -ne "") {
    $args += @("-target_name", $TargetName)
}

& $programFlash @args
