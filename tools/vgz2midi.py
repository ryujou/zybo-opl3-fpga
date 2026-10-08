"""Convert this project's OPL2/OPL3 VGZ collection with Vgm3Mid and mido."""
import argparse
import gzip
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc_player"))
from vgm_loader import load_vgm_file


def build_converter(destination):
    revision = "9e92dacbaa7de000e5ef6a6b8c98b889726b2f16"
    url = f"https://codeload.github.com/axelei/Vgm3Mid/zip/{revision}"
    with urllib.request.urlopen(url) as response:
        archive = response.read()
    with tempfile.TemporaryDirectory(prefix="opl3_vgm3mid_build_") as temp:
        directory = Path(temp)
        with zipfile.ZipFile(io.BytesIO(archive)) as source_zip:
            source_zip.extractall(directory)
        source = directory / f"Vgm3Mid-{revision}/src/main/java"
        package = source / "net/krusher/vgm3mid"
        config = package / "Config.java"
        config.write_text(config.read_text(encoding="utf-8")
                          .replace("CNV_ACCURACY = 0x10", "CNV_ACCURACY = 0xFF")
                          .replace("VGM_LOOPS = 2", "VGM_LOOPS = 1"), encoding="utf-8")
        opl = package / "chip/Ym3812.java"
        opl.write_text(opl.read_text(encoding="utf-8")
                       .replace("case 2: tempByt = MIDI_PAN_CENTER", "case 2: tempByt = MIDI_PAN_RIGHT")
                       .replace("case 3: tempByt = MIDI_PAN_RIGHT", "case 3: tempByt = MIDI_PAN_CENTER"),
                       encoding="utf-8")
        classes = directory / "classes"
        subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(classes),
                        *map(str, sorted(source.rglob("*.java")))], check=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as jar:
            jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\r\n"
                         "Main-Class: net.krusher.vgm3mid.Vgm3Mid\r\n\r\n")
            for file in sorted(classes.rglob("*.class")):
                jar.write(file, file.relative_to(classes).as_posix())
    print(f"Built {destination}")


def split_banks(source, directory):
    loaded = load_vgm_file(str(source))
    raw = gzip.decompress(source.read_bytes())
    opl3 = struct.unpack_from("<I", raw, 0x5C)[0] != 0
    clock = struct.unpack_from("<I", raw, 0x5C if opl3 else 0x50)[0]
    streams = [bytearray(), bytearray()]
    elapsed_us = samples = 0
    for event in loaded.events:
        elapsed_us += event.delta_us
        new_samples = round(elapsed_us * 44100 / 1_000_000)
        delay = new_samples - samples
        samples = new_samples
        while delay:
            wait = min(delay, 65535)
            for stream in streams:
                stream.extend(struct.pack("<BH", 0x61, wait))
            delay -= wait
        for write in event.writes:
            if write.bank == 1 and write.reg < 0x20:
                # Both passes need OPL3's mode bit; other global bank-1 writes
                # aren't operators or notes in these 2-op source files.
                if write.reg == 5:
                    for stream in streams:
                        stream.extend((0x5F, 5, write.value))
                if write.reg == 4 and write.value:
                    raise ValueError(f"4-op source is not supported: {source}")
                continue
            streams[write.bank].extend((0x5E if opl3 else 0x5A, write.reg, write.value))
    paths = []
    for bank in range(2 if opl3 else 1):
        header = bytearray(0x100)
        header[:4] = b"Vgm "
        struct.pack_into("<I", header, 8, 0x171)
        struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
        struct.pack_into("<I", header, 0x5C if opl3 else 0x50, clock)
        streams[bank].append(0x66)
        data = header + streams[bank]
        struct.pack_into("<I", data, 4, len(data) - 4)
        path = directory / f"bank{bank}.vgm"
        path.write_bytes(data)
        paths.append(path)
    return paths, loaded.total_us / 1_000_000


def merge_voices(bank_files, destination, duration):
    states = [[0, 100, 64, 0] for _ in range(18)]
    active = [None] * 18
    channels = [ch for ch in range(16) if ch != 9]
    owners = {ch: set() for ch in channels}
    settings = {ch: None for ch in channels}
    pending = []
    for bank, file in enumerate(bank_files):
        midi = mido.MidiFile(file)
        ticks = 0
        for order, msg in enumerate(mido.merge_tracks(midi.tracks)):
            ticks += msg.time
            if not msg.is_meta:
                pending.append((round(ticks * 22050 / midi.ticks_per_beat), bank, order, msg))
    pending.sort(key=lambda item: item[:3])
    result = mido.MidiFile(type=0, ticks_per_beat=22050)
    track = mido.MidiTrack()
    result.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=destination.stem))
    track.append(mido.MetaMessage("set_tempo", tempo=500000))
    track.append(mido.Message("sysex", data=(0x7E, 0x7F, 9, 1)))
    last_tick = tick = 0
    approximations = 0
    source_notes = 0

    def emit(msg):
        nonlocal last_tick
        track.append(msg.copy(time=tick - last_tick))
        last_tick = tick

    def configure(ch, state):
        old = settings[ch]
        program, volume, pan, bend = state
        for index, msg in enumerate((mido.Message("program_change", channel=ch, program=program),
                                     mido.Message("control_change", channel=ch, control=7, value=volume),
                                     mido.Message("control_change", channel=ch, control=10, value=pan),
                                     mido.Message("pitchwheel", channel=ch, pitch=bend))):
            if old is None or old[index] != state[index]:
                emit(msg)
        settings[ch] = tuple(state)

    def release(voice):
        if active[voice] is None:
            return
        ch, note, _, _ = active[voice]
        owners[ch].remove(voice)
        active[voice] = None
        if not any(active[v][1] == note for v in owners[ch]):
            emit(mido.Message("note_off", channel=ch, note=note))

    def start(voice, note, velocity):
        nonlocal approximations
        state = tuple(states[voice])
        same = [ch for ch in channels if settings[ch] == state]
        free = [ch for ch in channels if not owners[ch]]
        if same:
            ch = same[0]
        elif free:
            ch = free[0]
            configure(ch, state)
        else:
            # One USB cable has 15 melodic channels. Keep all note pitches
            # when the source needs more independent controller states.
            ch = min(channels, key=lambda c: (100000 * (settings[c][0] != state[0])
                     + abs(settings[c][3] - state[3]) + 16 * abs(settings[c][2] - state[2])
                     + abs(settings[c][1] - state[1])))
            approximations += 1
        output_note = max(0, min(127, round(note + (state[3] - settings[ch][3]) / 4096)))
        if not any(active[v][1] == output_note for v in owners[ch]):
            emit(mido.Message("note_on", channel=ch, note=output_note, velocity=velocity))
        owners[ch].add(voice)
        active[voice] = (ch, output_note, note, velocity)

    for tick, bank, _, msg in pending:
        if msg.channel == 9:
            emit(msg)
            continue
        if msg.channel > 8:
            raise ValueError(f"Unexpected converter channel: {msg.channel}")
        voice = bank * 9 + msg.channel
        if msg.type == "note_on" and msg.velocity:
            source_notes += 1
            release(voice)
            start(voice, msg.note, msg.velocity)
        elif msg.type == "note_off" or msg.type == "note_on":
            release(voice)
        else:
            old_state = tuple(states[voice])
            if msg.type == "program_change":
                states[voice][0] = msg.program
            elif msg.type == "pitchwheel":
                states[voice][3] = msg.pitch
            elif msg.type == "control_change" and msg.control in (7, 10):
                states[voice][1 if msg.control == 7 else 2] = msg.value
            else:
                continue
            if active[voice] is not None and old_state != tuple(states[voice]):
                ch, _, note, velocity = active[voice]
                if len(owners[ch]) == 1:
                    configure(ch, states[voice])
                else:
                    release(voice)
                    start(voice, note, velocity)
    tick = max(tick, round(duration * 44100))
    for voice in range(18):
        release(voice)
    for ch in range(16):
        emit(mido.Message("control_change", channel=ch, control=123, value=0))
    track.append(mido.MetaMessage("end_of_track"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.save(destination)
    checked = mido.MidiFile(destination)
    if not source_notes or not any(msg.type == "note_on" and msg.velocity for msg in checked):
        raise ValueError(f"Conversion produced no notes: {destination}")
    if abs(checked.length - duration) > 0.01:
        raise ValueError(f"Conversion duration mismatch: {destination}")
    return source_notes, approximations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "midi")
    parser.add_argument("--output", type=Path, default=ROOT / "midi/converted")
    parser.add_argument("--jar", type=Path, default=ROOT / "build/usb_midi/converter/vgm3mid.jar")
    parser.add_argument("--build-converter", action="store_true", help="download pinned Vgm3Mid source and compile its JAR (requires a JDK)")
    args = parser.parse_args()
    if args.build_converter:
        build_converter(args.jar)
        return
    if not args.jar.is_file():
        parser.error(f"Vgm3Mid converter JAR is missing: {args.jar}")
    files = sorted(args.source.rglob("*.vgz"))
    if not files:
        parser.error(f"No VGZ files in {args.source}")
    total_notes = total_approximations = 0
    with tempfile.TemporaryDirectory(prefix="opl3_vgm2mid_") as temp:
        directory = Path(temp)
        for index, source in enumerate(files, 1):
            banks, duration = split_banks(source, directory)
            bank_midis = []
            for bank in banks:
                output = bank.with_suffix(".mid")
                output.unlink(missing_ok=True)
                conversion = subprocess.run(
                    ["java", "-jar", str(args.jar), str(bank), "-o", str(output)],
                    check=True, capture_output=True, text=True, encoding="utf-8")
                if not output.is_file():
                    raise RuntimeError(conversion.stdout + conversion.stderr)
                bank_midis.append(output)
            destination = (args.output / source.relative_to(args.source)).with_suffix(".mid")
            notes, approximations = merge_voices(bank_midis, destination, duration)
            total_notes += notes
            total_approximations += approximations
            print(f"[{index}/{len(files)}] {destination.relative_to(args.output)}: "
                  f"{duration:.3f}s, notes={notes}, channel approximations={approximations}", flush=True)
    print(f"Converted {len(files)} files; source notes={total_notes}; "
          f"channel approximations={total_approximations}", flush=True)


if __name__ == "__main__":
    main()
