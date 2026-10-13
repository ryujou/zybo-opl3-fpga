"""Run with vitis -s to build the standalone BSP and FSBL from opl3.xsa."""
import atexit
import os
from pathlib import Path
import subprocess

import vitis

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "vitis_project"
XSA = ROOT / "fpga/build/opl3.xsa"
NAME = "opl3_platform"

if not XSA.is_file():
    raise FileNotFoundError(XSA)
client = vitis.create_client()


@atexit.register
def close_owned_server():
    # Vitis 2025.2 leaves its Java process holding the Windows workspace lock.
    server = client._serverObj
    if os.name == "nt" and server.cp is not None:
        server.channel.close()
        subprocess.run(["taskkill", "/PID", str(server.cp.pid), "/T", "/F"],
                       check=True, stdout=subprocess.DEVNULL)
        server.cp.wait()
        server.cp = None
    vitis.dispose()


client.set_workspace(path=str(WORKSPACE))
if (WORKSPACE / NAME / "vitis-comp.json").is_file():
    platform = client.get_component(name=NAME)
else:
    platform = client.create_platform_component(
        name=NAME, hw_design=str(XSA), os="standalone",
        cpu="ps7_cortexa9_0", domain_name="standalone_ps7_cortexa9_0")
result = platform.build()
if result != 0:
    raise RuntimeError(f"Vitis platform build failed: {result}")
