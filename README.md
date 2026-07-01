# Zybo OPL3 FPGA

这个仓库已经整理到 `Vivado/Vitis 2025.2`，当前主线开发方式是：

- 硬件：`Vivado 2025.2`
- 板端固件：`standalone bare-metal`
- 上位机：`Python + PySide6 + PyUSB`
- 下载方式：`JTAG 直下 bitstream + ELF`
- 数据链路：`USB bulk`

当前不依赖 `BOOT.bin`、SD 卡启动、Linux 或 PetaLinux。

## 当前能力

- 硬件链路保持不变：`PS -> AXI4-Lite -> opl3_fpga_v2_0 -> opl3`
- 音频输出仍走 Zybo 板载 `SSM2603 + I2S`
- 板端支持两类播放路径：
  - 板端 CLI 本地播放 `.dro/.imf`
  - PC 上位机加载 `.mid/.midi/.vgm/.vgz`，转换为 OPL 事件后通过 USB 上传到板端 DDR，再由板端本地定时播放
- PC 上位机界面为简体中文

## 目录

- `fpga/`
  - Vivado BD、约束、Tcl、bitstream 构建
- `software/src/`
  - 板端裸机播放器、USB 传输层、OPL 控制逻辑
- `pc_player/`
  - PC 侧中文上位机
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

产物：

- `vitis_project/imfplay_port/build/imfplay_port.elf`

`software/vitis_builder.py` 会同步 `software/src` 到 Vitis 应用目录后再构建，不需要手动复制源码。

### PC 上位机

建议使用 Python 3.11+：

```bash
pip install -r pc_player/requirements.txt
python pc_player/main.py
```

依赖：

- `PySide6`
- `mido`
- `pyusb`

## Windows 下 USB 驱动

上位机通过 `PyUSB` 访问自定义 USB 设备，不再使用串口。

默认设备标识：

- `VID = 0xCAFE`
- `PID = 0x4010`

如果 Windows 没有把设备绑定到可供 `libusb`/`PyUSB` 使用的驱动，需要给这个设备安装 `WinUSB`。常见做法是使用 Zadig 之类的工具把该 VID/PID 对应设备切到 `WinUSB`。

## JTAG 下载运行

### 方式 1：Vivado/Vitis 图形界面

1. 在 `Hardware Manager` 下载 `fpga/build/opl3.bit`
2. 在 `Vitis/XSDB` 下载并运行 `vitis_project/imfplay_port/build/imfplay_port.elf`

### 方式 2：XSCT 脚本

确保 `xsct` 在 `PATH` 中，然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File software/jtag/run_jtag.ps1
```

也可以手动指定文件：

```powershell
powershell -ExecutionPolicy Bypass -File software/jtag/run_jtag.ps1 `
  -Bitstream fpga/build/opl3.bit `
  -Elf vitis_project/imfplay_port/build/imfplay_port.elf
```

## 板端 CLI

板端仍保留串口 CLI 作为调试和本地文件播放入口：

- 波特率：`115200`
- 格式：`8-N-1`

典型输出：

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

`stream` 会进入传输模式。当前实现优先尝试 USB 传输，若 USB 不可用则回退到 UART 传输后端。

## PC 上位机使用流程

1. 用 JTAG 下载 `bitstream` 和 `elf`
2. 将板子切到 USB 连接方式并接入 PC
3. 打开 `pc_player/main.py`
4. 选择识别到的 `Zybo OPL3 USB` 设备
5. 点击“连接测试”
6. 选择本地 `.mid/.midi/.vgm/.vgz`
7. 点击“播放”

上位机行为：

- 通过 USB 枚举并连接板子
- 发送 `HELLO / ENTER_STREAM / RESET_OPL`
- 将整首曲目转换为 OPL 事件并分块上传到板端内存
- 发送 `PLAY_BUFFERED`
- 由板端本地按定时器播放

## 当前限制

- 当前上位机只支持“本地文件 -> 板端播放”
- 不支持 USB Audio / UAC
- 不支持 DAW / VST / 实时 MIDI 键盘
- 暂停/停止仍未实现为中途可打断的控制
- 当前仓库已经完成 USB 代码接入和软件构建验证，但若要确认枚举、上传和实际播放，仍需要上板联调

## 说明

- `BOOT.bin`、SD 卡镜像和 QSPI 烧录不是当前主开发路径
- 若只做联调，优先使用 JTAG 直下
- `D:\DATA\资料\graduation_project\ZYBO` 一类本地历史资料目录不属于正式构建依赖
