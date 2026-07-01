from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import config
from midi_backend.base import MidiBackendError, MidiBuildResult
from protocol import OplWrite
from vgm_loader import OplStreamEvent, load_vgm_file

PROJECT_URL = "https://github.com/SudoMaker/midi2vgm"
MAX_WRITES_PER_EVENT = 63


def _append_event(payload: bytearray, delay_us: int, writes: list[OplWrite]) -> int:
    if not writes:
        return 0

    chunk_count = 0
    offset = 0
    first_chunk = True
    while offset < len(writes):
        chunk = writes[offset : offset + MAX_WRITES_PER_EVENT]
        chunk_delay = int(delay_us) if first_chunk else 0
        payload.extend(chunk_delay.to_bytes(4, "little", signed=False))
        payload.append(len(chunk))
        for write in chunk:
            payload.extend([write.bank & 0x01, write.reg & 0xFF, write.value & 0xFF])
        offset += len(chunk)
        first_chunk = False
        chunk_count += 1

    return chunk_count


def _build_from_opl_events(events: list[OplStreamEvent], total_delay_us: int) -> MidiBuildResult:
    payload = bytearray()
    event_count = 0
    write_count = 0

    for event in events:
        if not event.writes:
            continue
        write_list = list(event.writes)
        event_count += _append_event(payload, event.delta_us, write_list)
        write_count += len(write_list)

    return MidiBuildResult(
        data=bytes(payload),
        event_count=event_count,
        write_count=write_count,
        total_delay_us=total_delay_us,
        backend_name="midi2vgm backend",
    )


def find_midi2vgm_executable() -> Path:
    configured = config.MIDI2VGM_EXE_PATH
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate.resolve()
        raise MidiBackendError(
            f"config.py 中设置的 MIDI2VGM_EXE_PATH 不存在: {candidate}\n项目地址：{PROJECT_URL}"
        )

    project_root = Path(__file__).resolve().parents[2]
    local_candidates = [
        project_root / "tools" / "midi2vgm" / "midi2vgm_opl3.exe",
        project_root / "tools" / "midi2vgm" / "midi2vgm_opl3",
        project_root / "tools" / "midi2vgm" / "midi2vgm.exe",
        project_root / "tools" / "midi2vgm" / "midi2vgm",
    ]
    for candidate in local_candidates:
        if candidate.is_file():
            return candidate.resolve()

    path_candidates = ["midi2vgm_opl3", "midi2vgm"]
    if os.name == "nt":
        path_candidates = ["midi2vgm_opl3.exe", "midi2vgm_opl3", "midi2vgm.exe", "midi2vgm"]
    for name in path_candidates:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()

    raise MidiBackendError(
        "未找到 midi2vgm_opl3，请将可执行文件放到 tools/midi2vgm/ 或在 config.py 中设置 MIDI2VGM_EXE_PATH。"
        f"项目地址：{PROJECT_URL}"
    )


def probe_midi2vgm_help(executable: Path) -> str:
    attempts = ([str(executable), "--help"], [str(executable), "-h"])
    errors: list[str] = []
    for cmd in attempts:
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=False)
        except OSError as exc:
            errors.append(f"{' '.join(cmd)}: {exc}")
            continue
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if output:
            return output
        errors.append(f"{' '.join(cmd)}: 无输出，返回码 {completed.returncode}")
    raise MidiBackendError(
        f"无法读取 midi2vgm 帮助信息：{' | '.join(errors)}\n项目地址：{PROJECT_URL}"
    )


def _infer_bank_args(help_text: str, bank_path: Path) -> list[str]:
    lower = help_text.lower()
    path_options = [
        "--bank-file",
        "--wopl",
        "--op2",
        "--ibk",
        "--bank-path",
        "--patch-file",
        "--patchset-file",
    ]
    for option in path_options:
        if option in lower:
            return [option, str(bank_path)]
    raise MidiBackendError(
        "当前 midi2vgm_opl3 帮助信息中未发现可接收外部 bank 文件路径的参数，无法使用 config.MIDI2VGM_BANK_PATH。"
        f"\n可执行文件帮助摘要：\n{help_text}\n项目地址：{PROJECT_URL}"
    )


def _stderr_tail(text: str, line_limit: int = 40) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "<empty>"
    return "\n".join(lines[-line_limit:])


def run_midi2vgm(input_mid: Path, output_vgm: Path, bank_path: Optional[Path]) -> Path:
    executable = find_midi2vgm_executable()
    help_text = probe_midi2vgm_help(executable)
    cmd = [str(executable), "--in", str(input_mid), "--out", str(output_vgm)]

    if bank_path is not None:
        cmd.extend(_infer_bank_args(help_text, bank_path))

    extra_args = list(config.MIDI2VGM_EXTRA_ARGS)
    if extra_args:
        cmd.extend(extra_args)

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=False)
    if completed.returncode != 0 or not output_vgm.is_file() or output_vgm.stat().st_size <= 0:
        raise MidiBackendError(
            "midi2vgm backend 执行失败。"
            f"\n项目地址：{PROJECT_URL}"
            f"\n可执行文件：{executable}"
            f"\n输入 MIDI：{input_mid}"
            f"\n输出 VGM：{output_vgm}"
            f"\n返回码：{completed.returncode}"
            f"\nstderr 摘要：\n{_stderr_tail(completed.stderr)}"
            f"\nstdout 摘要：\n{_stderr_tail(completed.stdout)}"
        )
    return executable


def build_with_midi2vgm(midi_path: str) -> MidiBuildResult:
    input_mid = Path(midi_path).resolve()
    if not input_mid.is_file():
        raise MidiBackendError(f"MIDI 文件不存在：{input_mid}")

    bank_path = Path(config.MIDI2VGM_BANK_PATH).resolve() if config.MIDI2VGM_BANK_PATH else None
    if bank_path is not None and not bank_path.is_file():
        raise MidiBackendError(f"config.py 中设置的 MIDI2VGM_BANK_PATH 不存在：{bank_path}")

    keep_temp = bool(config.MIDI2VGM_KEEP_TEMP)
    if keep_temp:
        temp_dir = Path(tempfile.mkdtemp(prefix="midi2vgm_"))
        temp_ctx = None
    else:
        temp_ctx = tempfile.TemporaryDirectory(prefix="midi2vgm_")
        temp_dir = Path(temp_ctx.name)

    try:
        output_vgm = temp_dir / f"{input_mid.stem}.vgm"
        executable = run_midi2vgm(input_mid, output_vgm, bank_path)
        loaded_vgm = load_vgm_file(str(output_vgm))
        built = _build_from_opl_events(loaded_vgm.events, loaded_vgm.total_us)
        built.diagnostic = (
            f"midi2vgm backend: exe={executable}; input={input_mid}; output={output_vgm}; "
            f"bank={bank_path if bank_path else '<default>'}"
        )
        if keep_temp:
            built.diagnostic += "; temp=kept"
        return built
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()
