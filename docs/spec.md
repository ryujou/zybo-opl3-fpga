# Zybo OPL3 双模式音源

同一裸机固件支持标准 USB-MIDI 和原始 VGM/VGZ 寄存器播放，声音从板载 SSM2603 输出。板载 SW0 关闭（0）为 MIDI，开启（1）为 VGM/VGZ；启动时读取，运行时支持切换。

版本基线固定为 **v1.0.0**。Windows VGM/VGZ 播放器提供单文件 EXE；固定固件、FPGA 配置及依赖版本随该 tag 发布。

- MIDI：USB-MIDI 1.0 Full Speed，EP1 OUT/IN 64 字节，一个 cable、16 通道，IN 空闲。VID/PID `CAFE:4013`，序列号 `ZOPL3MIDI0001`，Windows 系统 MIDI 类驱动，名称 `Zybo OPL3 MIDI`。
- MIDI 合成：固定 libADLMIDI `84d27bc2bdbd6dd249537a7f7d2450cbd402482e`，单 OPL3、bank 58、volume model 0、硬件左右声像。支持音符、力度、音色、控制器、弯音、触后和库支持的 SysEx；每约 1 ms 按实际经过时间推进。16 个 MIDI 通道不保证 16 个独立硬件复音。
- VGM/VGZ：电脑端解压和解析原文件，使用已有 USB Bulk 协议上传原始 OPL 寄存器与等待时间，板端 8 MiB 整曲缓冲并本地计时播放。绕过 GM 音色映射和 libADLMIDI，不转换为 MIDI。使用 `CAFE:4012`、`ZOPL3USB0001`、WinUSB，兼容现有 `pc_player`。
- 两种 USB 身份分别枚举，只有 VGM 模式发布 WinUSB 自动绑定描述符；不同时提供复合 MIDI/Bulk 接口。切换先停止和静音、清空上传与消息状态，USB 断开约两秒后重新枚举。SW0 经过双触发器同步与 20 ms 软件消抖。
- 中断仅接收和入队，DMA 保持缓存维护。USB 复位、取消配置、队列溢出和传输错误由主循环清音并清理状态。
- MIDI 8 KiB 事件队列、1 KiB SysEx 缓冲；超长 SysEx 丢弃至结束。VGM 使用独立 8 KiB 接收队列。ARM 不生成 PCM。
- 保留既有 OPL3、AXI、Codec 和 BSP；bitstream 增加 SW0 至 PS EMIO GPIO 的输入连接。heap 4 MiB、主栈 64 KiB。
- SD/QSPI 镜像包含匹配 FSBL、带 SW0 的 bitstream 和双模式 ELF，输出 `build/usb_midi/BOOT.bin`。QSPI 地址 0 写入并完整回读校验。

普通 MIDI 使用 Windows 播放器。VGM/VGZ 使用 `pc_player` 直接播放以保留源 FM 参数；Python MIDI 转换器作为可选桌面工具保留，转换仍属于近似映射。不包含 PetaLinux、USB 音频或 MIDI 2.0。

验收：两个模式的 Windows 驱动、切换与异常清音；目录内 86 首 VGZ 的寄存器和时长保持，选两首完整直接播放；MIDI 消息与代表性连续播放；SD/QSPI 冷启动。编译、数字链路和物理听感分别记录。
