"""Run with vitis -s to create/build the independent opl3_usb_midi component."""
import atexit
import os
from pathlib import Path
import shutil
import sys
import subprocess

import vitis

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import ROOT, HERE, LIB, OUT, PLATFORM, DEFINES, COMMON_SOURCES, LIB_SOURCES, build_boot

workspace = OUT / "vitis_workspace"
name = "opl3_usb_midi"
OUT.mkdir(parents=True, exist_ok=True)
os.chdir(OUT)
client = vitis.create_client()


@atexit.register
def close_owned_server():
    # Vitis 2025.2 on Windows kills only cmd.exe, leaving Java holding the workspace lock.
    server = client._serverObj
    if os.name == "nt" and server.cp is not None:
        server.channel.close()
        subprocess.run(["taskkill", "/PID", str(server.cp.pid), "/T", "/F"],
                       check=True, stdout=subprocess.DEVNULL)
        server.cp.wait()
        server.cp = None
    vitis.dispose()


client.set_workspace(path=str(workspace))
client.add_platform_repos(platform=str(PLATFORM.parent))
if (workspace / name / "vitis-comp.json").is_file():
    app = client.get_component(name=name)
else:
    app = client.create_app_component(
        name=name, platform=str(PLATFORM / "opl3_platform.xpfm"),
        domain="standalone_ps7_cortexa9_0", template="empty_application")

app_src = workspace / name / "src"
sources = COMMON_SOURCES + LIB_SOURCES
sources += [HERE / n for n in ("main.cpp", "usb_device.cpp", "timer.cpp")]
sources += [ROOT / "software/src" / n for n in ("opl_hw.cpp", "ssm2603.cpp")]


def relative(path):
    return '"${CMAKE_CURRENT_SOURCE_DIR}/' + Path(os.path.relpath(path, app_src)).as_posix() + '"'


cmake = f'''cmake_minimum_required(VERSION 3.16)
project(opl3_usb_midi LANGUAGES C CXX ASM)
find_package(common)
set(CMAKE_CXX_STANDARD 17)
set(sources
{chr(10).join(relative(p) for p in sources)}
)
add_dependency_on_bsp(sources)
add_executable(opl3_usb_midi.elf ${{sources}})
target_compile_definitions(opl3_usb_midi.elf PRIVATE {" ".join(DEFINES)})
target_compile_options(opl3_usb_midi.elf PRIVATE -O2 -g -Wall -Wno-psabi -ffunction-sections -fdata-sections)
target_include_directories(opl3_usb_midi.elf PRIVATE
{chr(10).join(relative(p) for p in (HERE, LIB / "include", LIB / "src", ROOT / "software/src"))}
)
set(linker_script {relative(ROOT / "software/src/lscript.ld")})
set_target_properties(opl3_usb_midi.elf PROPERTIES LINK_DEPENDS "${{linker_script}}")
target_link_directories(opl3_usb_midi.elf PRIVATE "${{CMAKE_LIBRARY_PATH}}")
target_link_options(opl3_usb_midi.elf PRIVATE
    "-T${{linker_script}}" -Wl,--gc-sections
    -Wl,--defsym,_HEAP_SIZE=0x400000 -Wl,--defsym,_STACK_SIZE=0x10000
    "-Wl,-Map,${{CMAKE_BINARY_DIR}}/opl3_usb_midi.map")
target_link_libraries(opl3_usb_midi.elf PRIVATE
    -Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lstdc++,-lc,-lm,-lgcc,--end-group)
print_elf_size(CMAKE_SIZE opl3_usb_midi)
'''
(app_src / "CMakeLists.txt").write_text(cmake, encoding="utf-8")
result = app.build()
if result != 0:
    raise RuntimeError(f"Vitis build failed: {result}")
OUT.mkdir(parents=True, exist_ok=True)
for suffix in ("elf", "map"):
    shutil.copy2(workspace / name / "build" / f"{name}.{suffix}", OUT / f"{name}.{suffix}")
build_boot()
