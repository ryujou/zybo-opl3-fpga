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

MIDI2VGM_BANK = None
# None 表示使用 midi2vgm 默认 bank。
# 可以填 58、"58" 等，具体取值可通过 midi2vgm_opl3 --show-banks 查看。

MIDI2VGM_BANK_PATH = None
# legacy unsupported。当前 SudoMaker/midi2vgm backend 使用 --bank 内置 bank 编号，
# 不支持直接传 WOPL/OP2/IBK 文件路径。

MIDI2VGM_EXTRA_ARGS = []
# 给高级用户追加参数。

MIDI2VGM_KEEP_TEMP = False
# 调试用，保留临时 .vgm。
