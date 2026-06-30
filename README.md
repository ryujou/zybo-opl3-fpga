# OPL3 FPGA for Zybo

这是一个面向 Digilent Zybo 开发板的 OPL3 FPGA 工程，核心目标是在 Zynq-7000 平台上复现 Yamaha YMF262（OPL3）FM 合成器，并提供一个可直接上板运行的播放器系统。

当前仓库已经整理为 `Vivado/Vitis 2025.2` 构建流程，并在 Zybo 板上完成了实际启动、串口交互和音频播放验证。

## 当前状态

- 构建工具链固定为 `Vivado 2025.2 + Vitis 2025.2`
- 已验证完整构建链：
  - `BD -> bitstream -> xsa -> Vitis app -> BOOT.bin`
- 已完成上板验证：
  - SD 启动成功
  - 串口 CLI 正常
  - `play doom_000.dro` 可实际出声

## 工程结构

- `fpga/`
  - FPGA 顶层设计、约束、Vivado Tcl、Block Design 脚本
- `software/`
  - 裸机播放器程序
  - `.dro` 音乐文件
  - `BOOT.bin` 打包所需的 `bif`
- `Makefile`
  - 顶层一键构建入口

## 系统接口

- 上位机通信：
  - `PROG/UART` 串口
  - `115200 8-N-1`
- PS 与 PL 通信：
  - `AXI4-Lite`
- 音频输出：
  - Zybo 板载 `SSM2603`
  - `I2S`

这个仓库当前走的是 `bare-metal` 路线，不依赖 `Linux` 或 `PetaLinux`。

## 主要产物

成功构建后会生成：

- `fpga/build/opl3.bit`
- `fpga/build/opl3.xsa`
- `vitis_project/opl3_platform/export/opl3_platform/sw/boot/fsbl.elf`
- `vitis_project/imfplay_port/build/imfplay_port.elf`
- `software/opl3dro/filesystem.mfs`
- `BOOT.bin`

## 依赖环境

### 1. AMD/Xilinx 工具链

- `Vivado 2025.2`
- `Vitis 2025.2`
- `bootgen`
- `mfsgen`

Windows 下建议保证以下目录已加入 `PATH`：

```text
<Vivado 2025.2 安装目录>\Vivado\bin
<Vitis 2025.2 安装目录>\Vitis\bin
<Vitis 2025.2 安装目录>\Vitis\gnuwin\bin
```

### 2. Digilent Zybo board files

虽然这个仓库可以直接基于器件型号 `xc7z010clg400-1` 构建，不依赖 `.xpr` 工程文件，但为了在 Vivado 中做板级识别和人工检查，仍建议安装官方 board files。

官方仓库：

- <https://github.com/Digilent/vivado-boards>

如果 `Vivado 2025.2` 没有自动识别 Zybo，可在 Tcl 中设置：

```tcl
set_param board.repoPaths {/path/to/vivado-boards/new/board_files}
```

官方 Zybo 参考资料：

- <https://digilent.com/reference/programmable-logic/zybo/reference-manual>

历史参考资料目录仅作为旧工程比对使用，不属于正式依赖。

## 构建方法

### 1. 可选：添加 `.dro` 音乐文件

把新的 `.dro` 文件放进：

```text
software/opl3dro
```

它们会在构建时被打进 `filesystem.mfs`。

### 2. 一键构建

在仓库根目录执行：

```bash
make
```

该命令会完成：

1. FPGA bitstream 构建
2. XSA 导出
3. Vitis 平台和裸机应用构建
4. `.dro` 文件系统镜像生成
5. `BOOT.bin` 打包

### 3. 只构建硬件

```bash
cd fpga
make bitstream
```

### 4. 清理

```bash
make clean
```

## 上板运行

### 1. 准备 SD 卡

- 将 SD 卡格式化为 `FAT32`
- 把生成的 `BOOT.bin` 复制到 SD 卡根目录

### 2. 设置启动方式

- 将 Zybo 启动模式拨到 `SD`

### 3. 连接串口

- 用 USB 线连接板子的 `PROG/UART`
- 电脑会枚举出一个串口设备

串口参数：

- 波特率：`115200`
- 数据位：`8`
- 校验位：`None`
- 停止位：`1`
- 流控：`None`

### 4. 启动

- 上电或按 `PS-SRST`

正常情况下串口会显示：

```text
Welcome to the OPL3 FPGA

Type 'help' for a list of commands
>
```

## 串口命令

目前已验证的命令包括：

- `help`
- `ls`
- `play FILENAME`

示例：

```text
> ls
doom_000.dro 73778
doom_001.dro 54434
...

> play doom_000.dro
DRO 2.0 file
```

## 已验证结果

本仓库当前版本已经在 Zybo 板上完成以下验证：

- `BOOT.bin` 从 SD 正常启动
- 串口 `COM` 口可交互
- `help` 命令正常响应
- `ls` 能列出 `filesystem.mfs` 中的 `.dro` 文件
- `play doom_000.dro` 可实际播放音频

## 说明

- 当前软件侧为 `standalone bare-metal`
- 不依赖 `PetaLinux`
- 不保留 `Vivado/Vitis 2023.2` 双版本兼容
- 默认调试流中不再依赖缺失的 `ila_0.xci`

## 许可证

本仓库沿用原项目许可证。具体请查看仓库中的许可证文件。
