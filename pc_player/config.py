from __future__ import annotations

MIDI_BACKEND = "auto"
# 可选值：
# "auto"：优先 midi2vgm，失败后回退 Python mapper
# "midi2vgm"：强制使用 midi2vgm，失败直接报错
# "python"：只使用旧 Python mapper

MIDI2VGM_EXE_PATH = None
# None 表示自动搜索：
# Windows: tools/midi2vgm/midi2vgm_opl3.exe, midi2vgm_opl3.exe, midi2vgm.exe
# Linux/macOS: tools/midi2vgm/midi2vgm_opl3, midi2vgm_opl3, midi2vgm

MIDI2VGM_BANK_PATH = None
# 可选 WOPL/OP2/IBK bank 路径。
# 如果 None，则使用 midi2vgm_opl3 自己的默认 bank 或默认行为。

MIDI2VGM_EXTRA_ARGS = []
# 给高级用户追加参数。

MIDI2VGM_KEEP_TEMP = False
# 调试用，保留临时 .vgm。
