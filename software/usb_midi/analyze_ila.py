"""Check the USB-MIDI ILA test captures and decode the outgoing I2S words."""
import csv
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "build/usb_midi/ila"
CLOCK = int(json.loads((OUT / "opl3_midi.ltx").read_text(encoding="utf-8"))
            ["ltx_root"]["ltx_data"][0]["debug_cores"][0]["clk_input_freq_hz"])


def read(label):
    with (OUT / f"{label}.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    assert "sample_valid" in rows[0][3], "Unexpected ILA probe layout"
    data = [[int(value, 16) for value in row[3:]] for row in rows[2:]]
    assert len(data) == 8192, f"{label}: incomplete capture ({len(data)} rows)"
    left = [row[1] | row[2] << 15 for row in data]
    right = [row[3] | row[4] << 15 for row in data]
    left = [value - 65536 if value & 32768 else value for value in left]
    right = [value - 65536 if value & 32768 else value for value in right]
    return data, left, right


def stats(values):
    mean = sum(values) / len(values)
    crossings = [index + (mean - values[index]) / (values[index + 1] - values[index])
                 for index in range(len(values) - 1) if values[index] <= mean < values[index + 1]]
    frequency = CLOCK / 256 * (len(crossings) - 1) / (crossings[-1] - crossings[0]) if len(crossings) > 1 and max(map(abs, values)) > 100 else None
    return {"min": min(values), "max": max(values),
            "rms": round(math.sqrt(sum(value * value for value in values) / len(values)), 3),
            "frequency_hz": round(frequency, 3) if frequency else None}


def decode_i2s(data):
    words = [[], []]
    bits = []
    channel = previous_ws = None
    for previous, row in zip(data, data[1:]):
        if previous[5] == 0 and row[5] == 1:
            ws, sd = row[6:8]
            if ws != previous_ws:
                channel, bits = ws, []
            elif channel is not None and len(bits) < 24:
                bits.append(sd)
                if len(bits) == 24:
                    value = 0
                    for bit in bits:
                        value = value << 1 | bit
                    words[channel].append(value - (1 << 24) if value & (1 << 23) else value)
            previous_ws = ws
    return words


result = {}
for label in ("left", "right", "stereo", "quiet"):
    data, left, right = read(label)
    assert all(row[0] == 1 for row in data), f"{label}: capture was not qualified by sample_valid"
    peak_l, peak_r = max(map(abs, left)), max(map(abs, right))
    if label == "left":
        assert peak_l > 100 and peak_r <= 1, "Left panning failed"
    elif label == "right":
        assert peak_r > 100 and peak_l <= 1, "Right panning failed"
    elif label == "stereo":
        assert peak_l > 100 and max(abs(a - b) for a, b in zip(left, right)) <= 1, "Stereo output failed"
    else:
        # The OPL3 operator uses one's-complement sign: a muted negative
        # carrier contributes -1. This flute case has at most two residual LSBs.
        assert peak_l <= 2 and peak_r <= 2, "Sound remains after MIDI reset"
    result[label] = {"samples": len(data), "left": stats(left), "right": stats(right)}

for label in ("stereo_i2s", "quiet_i2s"):
    data, left, right = read(label)
    words = decode_i2s(data)
    assert min(map(len, words)) >= 30, f"{label}: too few complete I2S words"
    for channel, pcm in enumerate((left, right)):
        pcm = [value for row, value in zip(data, pcm) if row[0]]
        serial = words[channel]
        # Account for the I2S double buffer and the partial frame at capture start.
        assert any(all(serial[index] == pcm[index + offset] << 5
                       for index in range(3, len(serial) - 3) if 0 <= index + offset < len(pcm))
                   for offset in range(-3, 4)), f"{label}: I2S channel {channel} differs from OPL3 PCM"
    rises = [index for index in range(1, len(data)) if data[index - 1][5] == 0 and data[index][5] == 1]
    assert all(b - a == 4 for a, b in zip(rises, rises[1:])), "Unexpected I2S bit clock"
    result[label] = {"left_words": len(words[0]), "right_words": len(words[1]),
                     "left_range": [min(words[0]), max(words[0])], "right_range": [min(words[1]), max(words[1])],
                     "sclk_hz": CLOCK / 4, "pcm_matches_i2s": True}

print(json.dumps(result, indent=2))
