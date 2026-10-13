from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import mido
from midi_backend.midi2vgm_backend import (
    build_with_midi2vgm,
    find_midi2vgm_executable,
    probe_midi2vgm_banks,
    probe_midi2vgm_help,
)
from midi_loader import load_midi_file
from midi_sanitizer import sanitize_midi_to_temp_or_bytes
from vgm_loader import load_vgm_file


def _print_config() -> None:
    print("[config]")
    print(f"MIDI_BACKEND={config.MIDI_BACKEND}")
    print(f"MIDI2VGM_EXE_PATH={config.MIDI2VGM_EXE_PATH}")
    print(f"MIDI2VGM_BANK={getattr(config, 'MIDI2VGM_BANK', None)}")
    print(f"MIDI2VGM_BANK_PATH={config.MIDI2VGM_BANK_PATH}")
    print(f"MIDI2VGM_KEEP_TEMP={config.MIDI2VGM_KEEP_TEMP}")
    print()


def _print_file_info(path: Path) -> None:
    print("[input]")
    print(f"path={path}")
    print(f"exists={path.is_file()}")
    if path.is_file():
        raw = path.read_bytes()
        print(f"size={len(raw)}")
        print(f"head32={raw[:32].hex(' ')}")
    print()


def _probe_mido(path: Path) -> None:
    print("[mido]")
    try:
        midi = mido.MidiFile(str(path))
        print(f"raw_open=ok format={midi.type} tracks={len(midi.tracks)} ticks_per_beat={midi.ticks_per_beat} length={midi.length}")
    except Exception as exc:
        print(f"raw_open=failed {exc.__class__.__name__}: {exc}")
        try:
            sanitized = sanitize_midi_to_temp_or_bytes(str(path))
            print(f"sanitized_path={sanitized}")
            midi = mido.MidiFile(str(sanitized))
            print(f"sanitized_open=ok format={midi.type} tracks={len(midi.tracks)} ticks_per_beat={midi.ticks_per_beat} length={midi.length}")
        except Exception as sanitize_exc:
            print(f"sanitized_open=failed {sanitize_exc.__class__.__name__}: {sanitize_exc}")
    print()


def _probe_backend(path: Path) -> None:
    print("[midi2vgm]")
    exe = find_midi2vgm_executable()
    print(f"exe={exe}")
    print("--help")
    print(probe_midi2vgm_help(exe))
    print("--show-banks")
    print(probe_midi2vgm_banks(exe))
    print()

    result = build_with_midi2vgm(str(path))
    print(f"diagnostic={result.diagnostic}")

    safe_input_mid = None
    safe_output_vgm = None
    for part in result.diagnostic.split(';'):
        part = part.strip()
        if part.startswith('safe_input_mid='):
            safe_input_mid = part.split('=', 1)[1]
        if part.startswith('safe_output_vgm='):
            safe_output_vgm = part.split('=', 1)[1]

    print(f"safe_input_mid={safe_input_mid}")
    print(f"safe_output_vgm={safe_output_vgm}")

    if safe_output_vgm:
        output_path = Path(safe_output_vgm)
        print(f"output_vgm_exists={output_path.is_file()}")
        if output_path.is_file():
            print(f"output_vgm_size={output_path.stat().st_size}")
            loaded = load_vgm_file(str(output_path))
            print(f"vgm_events={len(loaded.events)} vgm_total_us={loaded.total_us} vgm_title={loaded.title}")

    print(f"event_count={result.event_count}")
    print(f"write_count={result.write_count}")
    print(f"data_size={len(result.data)}")
    print(f"total_delay_us={result.total_delay_us}")
    print(f"backend_name={result.backend_name}")
    print()


def _probe_loader(path: Path) -> None:
    print("[loader]")
    song = load_midi_file(str(path))
    print(f"title={song.title}")
    print(f"source_path={song.source_path}")
    print(f"parsed_path={song.parsed_path}")
    print(f"sanitized_from={song.sanitized_from}")
    print(f"events={len(song.events)}")
    print(f"total_us={song.total_us}")
    print()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/diagnose_midi_backend.py path/to/song.mid")
        return 2

    path = Path(argv[1]).expanduser()
    _print_config()
    _print_file_info(path)
    _probe_mido(path)
    _probe_loader(path)
    _probe_backend(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
