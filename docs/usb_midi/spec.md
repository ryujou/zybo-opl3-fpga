# Zybo OPL3 USB-MIDI 音源

独立裸机应用 `opl3_usb_midi`，Windows 识别名称为 `Zybo OPL3 MIDI`，由 Windows 播放器发送 MIDI，声音从板载 SSM2603 输出。

- USB-MIDI 1.0，Full Speed，EP1 OUT/IN 最大包长 64 字节，一个 cable、16 个 MIDI 通道。IN 空闲。
- VID/PID `CAFE:4013`，序列号 `ZOPL3MIDI0001`，系统 MIDI 类驱动；不发布 WinUSB 描述符。
- libADLMIDI 固定提交 `84d27bc2bdbd6dd249537a7f7d2450cbd402482e`，单 OPL3、bank 58、volume model 0、硬件左右声像。
- 接收中断仅传输和入队；主循环解析、写 OPL3 寄存器，并每约 1 ms 按真实经过时间推进音色引擎。ARM 不生成 PCM。
- 8 KiB 事件队列、1 KiB SysEx 缓冲；溢出、USB 复位或取消配置触发主循环静音和状态清理。超长 SysEx 丢弃到结束。
- Note On/Off、力度、音色切换、控制器、弯音、两种触后及库支持的 SysEx；16 个 MIDI 通道不保证 16 个独立硬件复音。
- 复用现有 FPGA、AXI 接口、SSM2603 初始化及平台 BSP。应用 heap 4 MiB，主栈 64 KiB。
- SD 启动镜像仅包含 FSBL、OPL3 bitstream 和 MIDI ELF，输出至 `build/usb_midi/BOOT.bin`。

统一使用标准 USB-MIDI 音源。VGZ 在电脑上转换为普通 MIDI 后播放，原 Bulk/UART 播放器停用。范围不包括 PetaLinux、USB 音频、MIDI 2.0、额外 Bulk 接口、QSPI 烧录。

VGM/VGZ 转换使用纯 Python，提供 GUI 文件/目录选择、批量转换、输出目录、进度、取消和错误显示。首版支持本地 OPL2/OPL3 2-op 音乐，匹配固定 bank 58，输出标准 MIDI。

验收包括 Windows 11 系统 MIDI 驱动与播放器兼容性、16 通道与鼓组/控制器、30 分钟代表性 MIDI 播放且队列零溢出、停止/重连无挂音，以及脱离 JTAG 的 SD 冷启动。目录内全部 86 个 VGZ 转换为 MIDI，选取两首完整播放。物理板验证状态独立记录。
