"""Build the portable Windows VGM/VGZ player with PyInstaller 6.22.3."""
import argparse
import os
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libusb", required=True, type=Path,
                        help="path to the 64-bit libusb-1.0.dll to bundle")
    args = parser.parse_args()
    dll = args.libusb.resolve()
    if not dll.is_file():
        parser.error(f"libusb DLL not found: {dll}")
    output = ROOT / "dist/pc_player"
    work = ROOT / "build/pc_player"
    work.mkdir(parents=True, exist_ok=True)
    # Qt uses Windows ICU; resolve system DLLs before other SDKs on PATH.
    system32 = str(Path(os.environ["SystemRoot"]) / "System32")
    os.environ["PATH"] = system32 + os.pathsep + os.environ["PATH"]
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx",
        "--name", "ZyboOPL3Player", "--distpath", str(output),
        "--workpath", str(work / "pyinstaller"), "--specpath", str(work),
        "--add-binary", f"{dll}:.",
        "--add-data", f"{HERE / 'THIRD_PARTY.txt'}:licenses",
        str(HERE / "main.py"),
    ])
    print(output / "ZyboOPL3Player.exe")


if __name__ == "__main__":
    main()
