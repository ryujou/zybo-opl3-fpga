# midi2vgm backend

## 为什么不再把旧 Python mapper 作为主 MIDI 路线

仓库现有的 `gm_mapper.py` + `opl_allocator.py` 路线可以把 MIDI 直接映射成 OPL3 寄存器事件，但它本质上是项目内的简化 FM patch 方案：

- 音色映射较粗略。
- GM 乐器族只做了近似分类，不适合作为成熟的通用 MIDI→OPL3 合成主路线。
- 项目目标是提升 GM/OPL3 MIDI 播放质量，而不是继续维护一套自写的 FM 音色库。

因此当前默认策略改为：优先使用外部 `midi2vgm_opl3`，失败时再回退到旧 Python mapper。

## 工作流程

当前 MIDI backend 工作流如下：

`MIDI -> midi2vgm_opl3 -> 临时 VGM -> vgm_loader.py -> song_builder.py -> USB upload_song/play_buffered -> Zybo`

也就是说：

1. 上位机读取 `.mid/.midi`。
2. 优先调用 `SudoMaker/midi2vgm` 的 `midi2vgm_opl3`。
3. 生成临时 `.vgm` 文件。
4. 复用现有 `vgm_loader.py` 解析 OPL3 VGM 事件。
5. 复用现有 `song_builder.py` 生成板端预加载 event bytes。
6. 继续走原来的 USB 上传协议与 `play_buffered` 播放。

`.vgm/.vgz` 直接播放路径保持不变，不依赖 `midi2vgm`。

## 上游项目

- 项目地址：<https://github.com/SudoMaker/midi2vgm>

README 当前明确的 OPL3 工具名为 `midi2vgm_opl3`。

## 如何安装 / 编译 midi2vgm

请参考上游仓库 README：

- <https://github.com/SudoMaker/midi2vgm>

典型构建步骤（以 README 为准）：

```bash
git clone https://github.com/SudoMaker/midi2vgm
cd midi2vgm
mkdir build
cd build
cmake ..
make
```

Windows 用户可以用 Visual Studio / CMake 生成 `midi2vgm_opl3.exe`。

## 建议放置路径

### Windows

建议放到：

```text
tools/midi2vgm/midi2vgm_opl3.exe
```

### Linux / macOS

建议放到：

```text
tools/midi2vgm/midi2vgm_opl3
```

## config.py 配置

新增 `pc_player/config.py`：

```python
MIDI_BACKEND = "auto"
MIDI2VGM_EXE_PATH = None
MIDI2VGM_BANK_PATH = None
MIDI2VGM_EXTRA_ARGS = []
MIDI2VGM_KEEP_TEMP = False
```

### MIDI_BACKEND

可选值：

- `"auto"`：优先 `midi2vgm`，失败后回退到旧 Python mapper。
- `"midi2vgm"`：强制使用 `midi2vgm`，失败直接报错。
- `"python"`：只使用旧 Python mapper。

### MIDI2VGM_EXE_PATH

- `None`：自动搜索。
- 或填入 `midi2vgm_opl3` 可执行文件绝对/相对路径。

自动搜索顺序：

1. `config.MIDI2VGM_EXE_PATH`
2. 项目目录下：
   - `tools/midi2vgm/midi2vgm_opl3.exe`
   - `tools/midi2vgm/midi2vgm_opl3`
   - `tools/midi2vgm/midi2vgm.exe`
   - `tools/midi2vgm/midi2vgm`
3. `PATH` 中：
   - `midi2vgm_opl3`
   - `midi2vgm`

### MIDI2VGM_BANK_PATH

可选 WOPL / OP2 / IBK bank 路径。

注意：当前实现不会猜参数名。它会先读取 `midi2vgm_opl3 --help` / `-h`，只有在帮助信息中发现可接收“bank 文件路径”的参数时才会传递该路径。

如果当前版本 CLI 只支持 bank 编号、不支持外部文件路径参数，那么会直接报清楚错误，而不是静默忽略。

### MIDI2VGM_EXTRA_ARGS

给高级用户附加原始命令行参数。例如：

```python
MIDI2VGM_EXTRA_ARGS = ["--vol-model", "0"]
```

### MIDI2VGM_KEEP_TEMP

- `False`：默认删除临时 `.vgm`
- `True`：保留临时目录，方便调试 `midi2vgm` 输出

## 如何指定 WOPL / OP2 / IBK bank

如果你使用的 `midi2vgm_opl3` 版本在 `--help` 中暴露了外部 bank 文件参数，可在 `config.py` 中设置：

```python
MIDI2VGM_BANK_PATH = r"D:/banks/example.wopl"
```

如果 `--help` 中没有任何可识别的 bank 文件路径参数，当前 backend 会报错，提示这个版本无法从 CLI 推断如何传入外部 bank 文件。

项目不会把来源不明的 bank 文件直接塞进仓库。

## backend 模式区别

### auto

- 先尝试 `midi2vgm backend`
- 若失败，则回退 `python fallback`
- fallback 不静默，诊断信息里会包含失败原因

### midi2vgm

- 只使用 `midi2vgm backend`
- 缺少可执行文件、CLI 失败、输出 VGM 无效时直接报错

### python

- 只使用旧 Python mapper
- 不依赖 `midi2vgm`

## 错误信息包含哪些内容

当 `midi2vgm` 执行失败时，异常会尽量包含：

- midi2vgm 项目地址
- 使用的可执行文件路径
- 输入 MIDI 路径
- 输出 VGM 路径
- 返回码
- stderr 摘要
- stdout 摘要

## 已知限制

- 仍然是 OPL3 FM 合成，不是现代波表。
- 不保证完整 GS / XG / SysEx 兼容。
- 如果 `midi2vgm` 生成的 VGM 使用了当前 `vgm_loader.py` 不支持的命令，需要继续补 `vgm_loader.py`。
- 如果生成事件超过板端 preload capacity，会报错；后续如需更长曲目，需要再做流式播放或压缩方案。
- 本次改动没有修改 FPGA/板端协议，也没有修改 USB VID/PID、frame 格式、`upload_song`、`play_buffered`。

## 调试建议

1. 先确认 `.vgm/.vgz` 直接播放仍然正常。
2. 再把 `midi2vgm_opl3` 放到建议路径。
3. 必要时把 `MIDI2VGM_KEEP_TEMP = True`，检查临时 `.vgm` 是否能被当前 `vgm_loader.py` 正确解析。
4. 若失败，先运行：

```bash
midi2vgm_opl3 --help
```

确认你的版本是否支持所需参数。
