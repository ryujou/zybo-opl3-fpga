from pathlib import Path
import shutil

import vitis


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / "vitis_project"
HW_PLATFORM = REPO_ROOT / "fpga" / "build" / "opl3.xsa"
SOFTWARE_DIR = REPO_ROOT / "software"
PLATFORM_NAME = "opl3_platform"
APP_NAME = "imfplay_port"
DOMAIN_NAME = "standalone_ps7_cortexa9_0"


def get_or_create_platform(client):
    try:
        return client.get_component(name=PLATFORM_NAME)
    except Exception:
        return client.create_platform_component(
            name=PLATFORM_NAME,
            hw_design=str(HW_PLATFORM),
            os="standalone",
            cpu="ps7_cortexa9_0",
            domain_name=DOMAIN_NAME,
        )


def get_or_create_app(client, platform_xpfm):
    try:
        return client.get_component(name=APP_NAME)
    except Exception:
        return client.create_app_component(
            name=APP_NAME,
            platform=platform_xpfm,
            domain=DOMAIN_NAME,
            template="empty_application",
        )


def sync_app_sources():
    app_src = WORKSPACE / APP_NAME / "src"
    source_src = SOFTWARE_DIR / "src"
    app_src.mkdir(parents=True, exist_ok=True)
    for item in source_src.iterdir():
        target = app_src / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


client = vitis.create_client()
client.set_workspace(path=str(WORKSPACE))

platform = get_or_create_platform(client)
platform.build()

platform_xpfm = client.find_platform_in_repos(PLATFORM_NAME)
comp = get_or_create_app(client, platform_xpfm)
sync_app_sources()
comp.build()
