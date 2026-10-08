"""Build the dual-mode MIDI/VGM ELF and boot image, or run native tests."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LIB = ROOT / "third_party/libadlmidi"
OUT = ROOT / "build/usb_midi"
PLATFORM = ROOT / "vitis_project/opl3_platform/export/opl3_platform"
VITIS = Path(os.environ.get("XILINX_VITIS", "J:/FPGA/2025.2/Vitis"))
DEFINES = ["OPL_DUAL_MODE", "ADLMIDI_FPGA", "ADLMIDI_DISABLE_MIDI_SEQUENCER",
           "ADLMIDI_DISABLE_NUKED_EMULATOR", "ADLMIDI_DISABLE_DOSBOX_EMULATOR",
           "ADLMIDI_DISABLE_OPAL_EMULATOR", "ADLMIDI_DISABLE_JAVA_EMULATOR"]
LIB_SOURCES = [LIB / "src" / name for name in (
    "adlmidi.cpp", "adlmidi_load.cpp", "adlmidi_midiplay.cpp", "adlmidi_opl3.cpp",
    "adlmidi_private.cpp", "inst_db.cpp", "wopl/wopl_file.c")]
COMMON_SOURCES = [HERE / name for name in ("midi_parser.cpp", "midi_synth.cpp", "usb_descriptors.cpp")]


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="build and run native tests")
    parser.add_argument("--host-cxx", help="native C++ compiler for tests")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    includes = [HERE, LIB / "include", LIB / "src", ROOT / "software/src"]
    sources = COMMON_SOURCES + LIB_SOURCES
    flags = ["-O2", "-g", "-Wall", "-ffunction-sections", "-fdata-sections"]
    defines = list(DEFINES)
    if args.test:
        cxx = args.host_cxx or os.environ.get("CXX") or shutil.which("g++")
        if not cxx:
            parser.error("native compiler required: --host-cxx PATH or CXX")
        cxx = Path(cxx)
        cc = cxx.with_name(cxx.name.replace("g++", "gcc").replace("clang++", "clang"))
        sources += [HERE / "tests.cpp"]
        destination = OUT / "tests.exe"
        link_flags = ["-static"]
        obj_dir = OUT / "host_obj"
    else:
        bin_dir = VITIS / "gnu/aarch32/nt/gcc-arm-none-eabi/bin"
        cxx, cc = bin_dir / "arm-none-eabi-g++.exe", bin_dir / "arm-none-eabi-gcc.exe"
        bsp = PLATFORM / "sw/standalone_ps7_cortexa9_0"
        for path in (bsp / "include/xparameters.h", bsp / "lib/libxil.a", OUT / "opl3_dual.bit"):
            if not path.is_file():
                parser.error(f"missing platform artifact: {path}; build the existing OPL3 platform first")
        includes += [bsp / "include"]
        defines += ["SDT"]
        flags += ["-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard", "-Wno-psabi", f"-specs={bsp / 'Xilinx.spec'}"]
        sources += [HERE / name for name in ("main.cpp", "usb_device.cpp", "timer.cpp", "vgm_transport.cpp")]
        sources += [ROOT / "software/src" / name for name in ("opl_hw.cpp", "ssm2603.cpp", "opl_stream.cpp")]
        destination = OUT / "opl3_usb_midi.elf"
        link_flags = [f"-L{bsp / 'lib'}", f"-T{ROOT / 'software/src/lscript.ld'}",
                      "-Wl,--defsym,_HEAP_SIZE=0x400000", "-Wl,--defsym,_STACK_SIZE=0x10000",
                      f"-Wl,-Map,{OUT / 'opl3_usb_midi.map'}",
                      "-Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lstdc++,-lc,-lm,-lgcc,--end-group"]
        obj_dir = OUT / "arm_obj"
    obj_dir.mkdir(exist_ok=True)
    objects = []
    for index, source in enumerate(sources):
        obj = obj_dir / f"{index:02d}_{source.stem}.o"
        is_cpp = source.suffix == ".cpp"
        language_flags = ["-std=c++17"] if is_cpp else []
        run([cxx if is_cpp else cc, *flags, *language_flags,
             *[f"-D{d}" for d in defines], *[f"-I{p}" for p in includes], "-c", source, "-o", obj])
        objects.append(obj)
    run([cxx, *flags, *objects, "-Wl,--gc-sections", *link_flags, "-o", destination])
    if args.test:
        run([destination])
    else:
        run([bin_dir / "arm-none-eabi-size.exe", destination])
        build_boot()
    print(destination)


def build_boot():
    fsbl = PLATFORM / "sw/boot/fsbl.elf"
    bif = OUT / "usb_midi.bif"
    if not fsbl.is_file():
        raise FileNotFoundError(fsbl)
    bif.write_text('the_ROM_image:\n{\n'
                   f'  [bootloader] "{fsbl.as_posix()}"\n'
                   f'  "{(OUT / "opl3_dual.bit").as_posix()}"\n'
                   f'  "{(OUT / "opl3_usb_midi.elf").as_posix()}"\n'
                   '}\n', encoding="utf-8")
    run([VITIS / "bin/bootgen.bat", "-image", bif, "-arch", "zynq", "-o", OUT / "BOOT.bin", "-w", "on"])
    print(OUT / "BOOT.bin")


if __name__ == "__main__":
    main()
