"""Capture a held note, reconnect USB, check silence, and reopen the MIDI output."""
import csv
import os
from pathlib import Path
import subprocess
import time
import hardware_test as midi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/usb_midi/ila"


def capture(label):
    vivado = Path(os.environ.get("XILINX_VIVADO", "J:/FPGA/2025.2/Vivado")) / "bin/vivado.bat"
    subprocess.run([str(vivado), "-mode", "batch", "-source", str(ROOT / "software/usb_midi/capture_ila.tcl"),
                    "-log", str(OUT / f"{label}.log"), "-journal", str(OUT / f"{label}.jou"),
                    "-tclargs", label, "samples"], cwd=ROOT, check=True)
    with (OUT / f"{label}.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))[2:]
    assert len(rows) == 8192 and all(row[3] == "1" for row in rows), "Incomplete qualified capture"
    values = [int(row[low], 16) | int(row[sign], 16) << 15
              for row in rows for low, sign in ((4, 5), (6, 7))]
    return max(abs(value - 65536 if value & 32768 else value) for value in values)


index = next(index for index, name in midi.outputs() if name == "Zybo OPL3 MIDI")
handle = midi.C.c_void_p()
midi.check(midi.api.midiOutOpen(midi.C.byref(handle), index, 0, 0, 0), "open MIDI output")
try:
    midi.sysex(handle, [0xF0, 0x7E, 0x7F, 9, 1, 0xF7])
    midi.short(handle, 0xC0, 73)
    midi.short(handle, 0x90, 69, 100)
    time.sleep(1)
finally:
    # Keep the note held on the board so USB reset, rather than host cleanup, must silence it.
    midi.check(midi.api.midiOutClose(handle), "close MIDI output")
assert capture("reconnect_before") > 100, "The test note was not held before disconnect"
vitis = Path(os.environ.get("XILINX_VITIS", "J:/FPGA/2025.2/Vitis")) / "bin/xsct.bat"
subprocess.run([str(vitis), str(ROOT / "software/usb_midi/hardware_reconnect.tcl")], cwd=ROOT, check=True)
time.sleep(5)
assert capture("reconnect_quiet") <= 2, "A note remains after USB reset"
index = next(index for index, name in midi.outputs() if name == "Zybo OPL3 MIDI")
with midi.device(index) as handle:
    midi.short(handle, 0xB0, 123, 0)
print("USB-MIDI re-enumerated, held note cleared, and output reopened")
