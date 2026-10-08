# 构建、连接与启动

适用现有原版 Zybo / XC7Z010 / SSM2603 工程。以下命令在仓库根目录运行；项目文件位置由脚本相对自身路径计算。

## 构建

工具链为现有 Vitis 2025.2。依赖现有 `fpga/build/opl3.bit` 和 `vitis_project/opl3_platform/export/opl3_platform` 中的 BSP、XPFM、FSBL。库源码位于 `third_party/libadlmidi`，不从网络下载，也不使用上位机缓存。

`firmware/usb_midi` 提供本机验收的 `opl3_usb_midi.elf` 和 SD 启动镜像 `BOOT.bin`。可以直接使用预编译镜像；源码构建产物仍输出到 `build/usb_midi`。

```powershell
$env:XILINX_VITIS = 'J:/FPGA/2025.2/Vitis'
python -B software/usb_midi/build.py
```

产物：`build/usb_midi/opl3_usb_midi.elf`、链接 map、`usb_midi.bif`、`BOOT.bin`。Bootgen 只写该子目录。

创建并构建 Vitis 独立应用：

```powershell
& "$env:XILINX_VITIS/bin/vitis.bat" -s software/usb_midi/vitis_app.py
```

Vitis workspace 位于 `build/usb_midi/vitis_workspace`，应用名 `opl3_usb_midi`，引用原平台的导出文件及仓库源码，产物同样导出到 `build/usb_midi`。本项目的使用入口统一为 USB-MIDI。

主机测试使用原生 GCC 或 LLVM-MinGW（不是 ARM 编译器）：

```powershell
python -B software/usb_midi/build.py --test --host-cxx 'J:/lumia/FPGA/OPL3/opl3_host/tools/llvm-mingw/llvm-mingw-20260616-ucrt-x86_64/bin/g++.exe'
```

也可将 `CXX` 设置为本机编译器路径。测试输出在 `build/usb_midi/tests.exe`。

## 连接

1. 将板设为 USB 外设模式：原版 Zybo 的 **J9 USB OTG Micro-AB** 接 Windows，**JP1 断开**。J11 是 JTAG/UART 接口，用于下载、串口或独立供电；不能承载本固件的 MIDI 数据。供电源由 JP7 选择。
2. 耳机或有源音箱连接黑色 **J5 Headphone Out**。
3. 固件启动成功后串口输出 `USB-MIDI ready: CAFE:4013, bank 58`。定时器、Codec 或合成/USB 初始化失败会打印错误并退出。
4. 在 MIDI 播放器的输出设置中选择 `Zybo OPL3 MIDI`，打开 `.mid` 并播放。应由 Windows 系统 MIDI 类驱动识别；不为 `CAFE:4013` 绑定 WinUSB。

开源播放器可使用 [Cynthia](https://github.com/blaiz2023/Cynthia)（MIT，Windows 便携程序）或 [Drumstick MIDI File Player](https://github.com/pedrolcl/dmidiplayer)（GPLv3，Windows 外部 MIDI 输出）。本机实测 Cynthia，程序位于 `build/usb_midi/players/cynthia.exe`。Settings 中选择该设备；Play List 的 Paste 可以导入复制的 MIDI 文件绝对路径。Drumstick 和 Falcosoft 的界面尚未实测。

## VGZ 转 MIDI

本机转换结果位于 `midi/converted`，与原 VGZ 保持相同的专辑子目录和文件名。输入音乐和转换结果是本地素材，不纳入版本控制。输出是普通 SMF MIDI，不包含私有寄存器 SysEx。

```powershell
python -m pip install mido PySide6
python -B tools/vgz2midi_gui.py
# 命令行批量转换，默认读取 midi 并输出到 midi/converted：
python -B tools/vgz2midi.py
```

`tools/vgz2midi.py` 为纯 Python 转换核心，命令行只依赖 `mido`；`tools/vgz2midi_gui.py` 使用 PySide6。GUI 支持选择多个文件或文件夹、指定输出、保留子目录、显示进度与逐文件结果、停止转换。输出中同名 MIDI 会覆盖；不同输入指向同一输出时会明确报错。转换过程中窗口保持响应，单个失败不阻断其余文件。

核心直接解析 OPL2/YM3812、OPL3/YMF262 的 2-op 寄存器和 OPL 节奏模式，以整数 44.1 kHz 采样数保留时间，输出 22050 ticks/quarter、500000 µs/quarter 的单次播放 SMF。音色参数匹配固定 libADLMIDI bank 58，精确匹配优先，其余匹配相近的旋律音色；对应音色的移调量用于还原 MIDI 音高。电平、左右声像和弯音映射为标准 MIDI 控制消息，鼓组使用通道 10。匹配表 `tools/opl_gm_bank58.json` 来源及许可证随表记录；转换工具按 GPL-3.0-or-later 提供，许可证见 `third_party/libadlmidi`。

OPL3 两组寄存器的 18 个声部均参与转换。相同音色、音量、声像和弯音可以共享 MIDI 通道；独立状态超过 15 组时近似合并。输出保留完整时长并补齐 Note Off。本工具不接受 4-op、双芯片及非 OPL 芯片指令，失败时显示具体原因。

VGZ 的 FM 音色转换为 GM Program 后只是近似，声部合并也可能改变包络或弯音；转换结果不承诺重现原始 VGZ 的音色或波形。板端依然按固定 bank 58 合成。

转换核心验证：`python -B tools/test_vgz2midi.py`。当前 Python 输出的主机验证与板卡验收状态见 `progress.md`。

接口与跳线依据 [Digilent Zybo 手册，USB OTG、音频及启动章节](https://digilent.com/reference/_media/reference/programmable-logic/zybo/zybo_rm.pdf)。USB 数据布局依据 [USB-MIDI 1.0 规范](https://www.usb.org/sites/default/files/midi10.pdf)。

## JTAG 验证

连接 J11，在独占板卡的下载时段内操作。使用运行于本机端口 3121 的 `hw_server`，下载脚本会复位 PS 并配置 FPGA：

```powershell
& "$env:XILINX_VITIS/bin/xsct.bat" software/usb_midi/hardware_download.tcl
```

若尚未运行硬件服务，可用 `Start-Process "$env:XILINX_VITIS/bin/unwrapped/win64.o/hw_server.exe" -ArgumentList '-s','tcp::3121' -WindowStyle Hidden` 启动。固件初始化时保持 USB 断开约两秒；串口出现 ready 后等待 Windows 枚举完成。

Windows 原生 MIDI 接口用例与板端统计：

```powershell
python -B software/usb_midi/hardware_test.py --list
python -B software/usb_midi/hardware_test.py --seconds 30
& "$env:XILINX_VITIS/bin/xsct.bat" software/usb_midi/hardware_stats.tcl
```

用例覆盖 16 通道、鼓组、128 音色、控制器、触后、超长 SysEx 丢弃及其后的 GM Reset，并提供密集短消息负载。超长 SysEx 用例应使串口 `sysex` 计数增加一次，其余错误应为零。`hardware_test.py --midi FILE.mid --seconds 1800` 可重复播放文件；此选项使用主机上的 `mido`，固件正常播放不依赖 Python。

## ILA 验证

测试镜像单独输出到 `build/usb_midi/ila`，正式 `BOOT.bin` 使用原来的 `fpga/build/opl3.bit`。ILA 采集 PCM、sample_valid 和 I²S 信号，深度 8192；采样模式按 sample_valid 筛选，I²S 模式采集连续时钟。硬件目标固定为本机 Zybo 的 JTAG 序列号 `210279540276`，JTAG 时钟设为 2 MHz。

```powershell
$midiVivado = 'J:/FPGA/2025.2/Vivado/bin/vivado.bat'
& $midiVivado -mode batch -source software/usb_midi/build_ila.tcl -log build/usb_midi/build_ila.log -journal build/usb_midi/build_ila.jou
& "$env:XILINX_VITIS/bin/xsct.bat" software/usb_midi/hardware_download.tcl build/usb_midi/ila/opl3_midi.bit
# 等待 USB 枚举完成。
python -B software/usb_midi/hardware_test.py --ila
python -B software/usb_midi/hardware_reconnect.py
& "$env:XILINX_VITIS/bin/xsct.bat" software/usb_midi/hardware_download.tcl
```

`--ila` 自动保持 A4/program 73 测试音，验证左、右、双侧输出及停止后的残差，并将 I²S 解码值与同时捕获的 OPL3 PCM 对照。CSV 保存在该子目录；`analyze_ila.py` 可离线重查。重连用例先确认音符仍保持，再停用 USB 控制器两秒；固件应自行清音，Windows 应重新枚举且 MIDI 输出可再次打开。该用例验证软件断开与总线复位，物理拔插仍需单独验收。

## SD 启动

将 `build/usb_midi/BOOT.bin` 放入 FAT32 microSD 卡根目录。断电后插入 J4，将 JP5 置于丝印 `SD` 位置，按 JP7 选择的供电源重新上电。镜像自带 FPGA 配置和应用，不需要 DRO 文件系统或 MIDI 文件。

更换启动模式需断电重启；仅按复位按钮不会重新采样 JP5。SD 启动时可以不接 JTAG，J9 保持与电脑连接。

## 实现与测量

- `usb_device.cpp`：XUsbPs、DMA 缓存维护、1024 个带时间戳的事件槽（保留一个空槽），复位/异常通知。
- `midi_parser.cpp`：CIN/cable 验证、分包 SysEx、CIN 0xF 字节流及 running status。
- `midi_synth.cpp` / `fpga_chip.h`：库实时 API、全局定时器推进及 FPGA 寄存器后端。
- `timer.cpp`：SCU 定时器初始化及 BSP 全局计时启动；`main.cpp` 按实际经过的微秒推进 `TickIterators()`。
- 库的 FPGA 适配说明见 `third_party/libadlmidi/LOCAL.txt`，软件 OPL 模拟器及 MIDI 文件 sequencer 不参与编译。

串口在错误计数变化时报告 `overflow/malformed/invalid/sysex/control`。Vitis 调试器中可读取 `midi_processed_events`、`midi_max_dispatch_us` 和 `midi_max_handler_us`：前者为处理的事件包数，后两者分别是从板端接收回调到开始处理的最大排队时间、单个事件处理的最大耗时。它们不包含 Windows 调度、USB 到达接收回调以前的时间或模拟音频输出延迟。统计从启动累计，单次处理耗时包含被 USB 中断抢占的时间。

`hardware_stats.tcl` 根据当前 ELF 的符号读取统计，不停止 ARM；运行镜像须与该 ELF 一致。下载脚本在启动前填充主栈标记，统计脚本读取其水位；heap 使用量来自 newlib 的最大 sbrk 申请量。这些指标分别度量主栈被写入的范围和 heap 已申请的空间，主栈测量不包含独立的 IRQ 等异常栈。为了测量演奏延迟，连续播放期间只监看串口，在播放结束后读取 JTAG 统计。

硬件验收时连续播放至少 30 分钟，记录曲目、时长、错误计数、两项延迟及 heap/stack 使用情况。停止测试需确认播放器实际发送 Note Off、All Notes Off 或 Reset；仅停止发送数据不会自动释放仍按住的音符。
