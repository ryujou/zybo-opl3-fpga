param()

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
$bootgen = Find-Tool "bootgen"
$bif = Join-Path $repoRoot "software/bif/imfplay_port.bif"
$bootBin = Join-Path $repoRoot "BOOT.bin"

& $bootgen -image $bif -arch zynq -o $bootBin -w on

Write-Host ("Generated {0}" -f $bootBin)
