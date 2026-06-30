# Zybo OPL3 FPGA

这是一个面向 Digilent Zybo 的 OPL3 FPGA 项目，当前仓库已经整理到 `Vivado/Vitis 2025.2`，并新增了两条可用的软件路径：

- 板端裸机 CLI，本地播放 `.dro/.imf`
- PC 中文上位机，通过串口实时发送 MIDI 转换后的 OPL3 事件

当前默认开发方式是 `JTAG 直下 bitstream + ELF`，不依赖 `BOOT.bin`。

## 当前能力

- 硬件仍是 `PS -> AXI4-Lite -> opl3_fpga_v2_0 -> opl3`
- 音频仍走 Zybo 板载 `SSM2603 + I2S`
- 板端仍是 `standalone bare-metal`
- 不依赖 `Linux` 或 `PetaLinux`
- 保留原来的串口命令：
  - `help`
  - `ls`
  - `play FILENAME`
- 新增串流命令：
  - `stream`

## 目录

- `fpga/`
  - Vivado BD、约束、Tcl、bitstream 构建
- `software/src/`
  - 板端裸机播放器与实时串流固件
- `pc_player/`
  - PC 侧中文 MIDI 上位机
- `software/jtag/`
  - XSCT/JTAG 下载脚本

## 构建

### 硬件

```bash
cd fpga
make bitstream
```

产物：

- `fpga/build/opl3.bit`
- `fpga/build/opl3.xsa`

### 板端软件

```bash
vitis -s software/vitis_builder.py
```

典型产物：

- `vitis_project/imfplay_port/build/imfplay_port.elf`

### PC 上位机

建议使用 Python 3.11+。

```bash
pip install -r pc_player/requirements.txt
python pc_player/main.py
```

依赖：

- `PySide6`
- `mido`
- `pyserial`

## JTAG 下载运行

### 方式 1：Vivado/Vitis 图形界面

1. 在 Hardware Manager 下载 `fpga/build/opl3.bit`
2. 在 Vitis/XSDB 下载并运行 `imfplay_port.elf`

### 方式 2：XSCT 脚本

确保 `xsct` 在 `PATH` 中，然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File software/jtag/run_jtag.ps1
```

也可以手工指定文件：

```powershell
powershell -ExecutionPolicy Bypass -File software/jtag/run_jtag.ps1 `
  -Bitstream fpga/build/opl3.bit `
  -Elf vitis_project/imfplay_port/build/imfplay_port.elf
```

## 板端命令行

串口命令模式仍使用：

- 波特率：`115200`
- 格式：`8-N-1`

启动后典型输出：

```text
Welcome to the OPL3 FPGA

Type 'help' for a list of commands
>
```

可用命令：

- `help`
- `ls`
- `play doom_000.dro`
- `stream`

`stream` 命令会把板子切到实时串流模式，随后串口波特率切换为 `921600`。

## PC 中文上位机

第一版流程：

1. 用 JTAG 下载 `bitstream` 和 `elf`
2. 打开 `pc_player/main.py`
3. 选择 Zybo 对应串口
4. 点击“连接测试”
5. 选择本地 `.mid/.midi`
6. 点击“播放”

上位机会先用 `115200` 发送 `stream` 命令，再自动切到 `921600` 二进制协议。

当前已实现：

- 中文界面
- 本地 MIDI 文件加载
- GM 到固定 OPL3 音色映射
- 播放 / 暂停 / 停止 / 重新开始
- 板端实时 OPL 事件串流

当前限制：

- 第一版只支持本地 MIDI 文件播放
- 不支持 USB Audio
- 不支持 DAW / VST / 实时 MIDI 键盘
- 暂停恢复会重建当前发声状态，但不会精确恢复原始包络相位

## 说明

- `BOOT.bin`、SD 卡镜像和 QSPI 烧录不是当前开发主路径
- 如果你只做联调，优先使用 JTAG 直下
- 若串口桥在 `921600` 下不稳定，可先降到 `460800` 做联调，再回到默认值排查
