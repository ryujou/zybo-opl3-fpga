# 实际验证状态

验证日期：2026-10-08。开发板为原版 Zybo / XC7Z010，Windows 11 Pro 26200。JTAG 与 USB OTG 已连接。

当前冻结版本为 **v1.0.0**。以下记录实际测量结果与验证边界。

## 构建与主机测试

- 固定版本 libADLMIDI、FPGA 寄存器后端、bank 58 实时合成、USB-MIDI 描述符与传输、消息解析及异常静音均已完成。
- 原生测试通过：描述符长度、AC/MS 接口和 jack/端点关联，CIN/cable 检查、多事件传输、分包/超长/畸形 SysEx、CIN 0xF 字节流及 running status。
- 合成测试通过：128 音色、16 通道含鼓组、力度零 Note Off、延音、弯音、硬件声像、超额声部、GM Reset 和无输入时的时间推进。USB 解析产生的寄存器写入与相同库版本和设置的直接 API 参考结果一致。
- ARM 独立构建、Vitis `opl3_usb_midi` 构建及 Bootgen 打包通过。正式 ELF、map 和 SD 启动镜像位于 `build/usb_midi`。
- 冻结检查通过：独立平台 BSP/FSBL 入口与 ARM/Bootgen 构建；播放器 4 项回归、转换器 9 项测试。

## Windows EXE

- `dist/pc_player/ZyboOPL3Player.exe` 为单文件窗口程序，包含 Python 3.11.9、PySide6 6.11.1、PyUSB 1.3.1 和 libusb 1.0.24；使用 PyInstaller 6.22.3 构建。
- 在项目外含中文和空格的目录中启动成功。进程的 Python、Qt 和 libusb 路径均位于自身解包目录，Windows ICU 使用系统库；界面能显示 OPL3 USB 设备。
- VGM/VGZ 加载与采样时间、超过 63 次同时写入的分包、自动连接和重新加载文件的回归测试均通过。EXE 的演奏链路沿用已验收的原始 USB 协议。

## Windows 与开发板

- Windows 自动枚举为 `Zybo OPL3 MIDI`，系统 USB MIDI 类驱动 `usbaudio`，设备状态正常；USB 控制器状态确认 Full Speed。
- Windows WinMM 可以列出、打开设备并发送短消息和 SysEx；16 通道、鼓组、128 音色、控制器、触后及 GM Reset 用例通过。故意发送的超长 SysEx 使丢弃计数增加一次，后续消息仍正常。
- Cynthia 1.00.6228（MIT）能选择该输出设备，打开外部 `.mid` 并演奏。已播放普通 MIDI 和 VGZ 转换结果；高频控制消息下未出现队列溢出。
- ILA 验证左、右、双侧声像、停止后静音；解码的 I²S 数据与 OPL3 PCM 左移 5 位一致。软件停用 USB 两秒后能自行清音、重新枚举并再次打开 MIDI 输出。

## 连续播放与资源

使用 Mutopia 的巴赫《勃兰登堡协奏曲第 2 号》三个 MIDI 分谱，经 Windows WinMM 连续发送 1800 秒，共 51477 条 MIDI 消息。连续播放期间未读取 JTAG，结束后读取统计：

| 指标 | 实测 |
| --- | --- |
| 处理 / 接收 USB-MIDI 事件包 | 52391 / 52391 |
| 队列溢出 / 畸形传输 / USB 发送错误 | 0 / 0 / 0 |
| 最大板端排队时间 | 756 µs |
| 单事件最大处理耗时 | 106 µs |
| newlib 最大 sbrk 申请量 | 387360 字节 |
| 主栈写入水位 | 11528 字节 |
| heap / 主栈预留 | 4 MiB / 64 KiB |

排队时间从板端接收回调开始计量，不包含 Windows 调度、USB 到达回调以前的时间或模拟音频延迟。主栈水位不包含 IRQ 等独立异常栈。歌曲来源见 [Mutopia 作品页](https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1680)。

## VGZ 转换与两首演奏

- 纯 Python 命令行与 PySide6 GUI 均完成 `midi` 内全部 86 个 VGZ 到 `midi/converted` 的转换，保留专辑目录；84 个 OPL3 文件的两组寄存器均参与转换。
- 当前 Python 输出为普通 SMF MIDI，共 376573 个音符、1234936 个事件，Note On/Off 配对完整；输出时长与 VGM 头部的 44.1 kHz 样本计数一致。FM 到 GM 音色及超过 15 组独立通道状态时的合并为近似转换。
- 转换核心 9 项测试通过，覆盖 DRO2MIDI 参考评分、Doom 吉他/鼓组识别、bank 58 匹配、音高/音量/声像/弯音、同时间戳 Key On/Off、共享同音、18 声部、节奏鼓组、采样时间、中文路径、VGZ、取消、畸形输入与 4-op 拒绝。
- 音色比较函数按固定提交 `c3890a869413282e590a2341d00aded24475cd9a` 的 DRO2MIDI `compareinstr()` 实现；与原 C++ NormalInstrument/BassDrum 评分对照 32761 组标准化输入，全部一致。Doom 源签名来自固定版本 libADLMIDI 的 DMX bank 14、16。
- 《At Doom’s Gate》转换结果含过载吉他 GM program 29、失真吉他 30、贝斯 34，以及 MIDI 通道 10 的鼓组；没有 Honky-tonk Piano/program 3 的音符。未知音色和固定 bank 58 的音色差异仍属于近似转换。
- GUI 整批转换成功 86/86，转换期间窗口持续响应；逐文件失败显示、失败后继续处理、取消和控件恢复均通过实测。
- 两首当前转换 MIDI 已通过 Cynthia All Once 完整演奏，板端处理/接收包 24605/24605，溢出、畸形传输和发送错误均为零。GM 音色近似不代表原始 FM 听感。

## SW0 双模式与原始 VGM/VGZ

- `build_switch.tcl` 生成带 SW0 的 bitstream，布局布线和时序通过，bitstream DRC 为零错误。固件和三分区启动镜像已构建。
- 板上读取 SW0 为 1，启动即枚举 `CAFE:4012` / `Zybo OPL3 USB Interface`，Windows 服务为 `WINUSB`。原播放器能完成 HELLO、上传、播放和状态查询。
- 调试器触发切换至 `CAFE:4013` / `Zybo OPL3 MIDI`，Windows 系统类驱动正常；16 通道、鼓组、128 音色、控制器、触后、SysEx 和复位用例通过。两种身份分别枚举。
- 全部 86 个原始 VGZ 能生成直接 OPL 播放数据，时长与头部采样数一致，均在 8 MiB 缓冲容量内。时间按累计采样数转换，保留末尾等待。
- 原始《Introduction》98.600000 秒、10908 个事件、24503 次寄存器写入；《At Doom’s Gate》96.513197 秒、3560 个事件、27752 次写入，均通过 USB Bulk 完整演奏。主机完成检测为 98.766/96.765 秒，包含轮询间隔。
- 两首播放后队列溢出、畸形输入和 USB 发送错误均为零；Doom 3560 个事件全部执行。最大 sbrk 申请 385504 字节，主栈写入水位 11528 字节。直接 VGM 模式绕过 MIDI 音色引擎。
- 暂停/继续/停止、演奏中切换 VGM→MIDI、MIDI→VGM 后空状态和重新握手均通过。主机放弃读取 Bulk IN 应答时，固件有界退出并取消旧传输，后续 HELLO 恢复。
- ARM 脚本构建和 Vitis 独立目标构建均通过；应用 text 432374、data 3492、bss 12757600 字节（包含 8 MiB 曲目缓冲及预留 heap/stack）。

## QSPI

- 检测到板载 Spansion S25FL128S，容量 16 MiB，页大小 256 字节、擦除扇区 64 KiB。
- `firmware/BOOT.bin` 共 2654348 字节，从地址 0 写入；擦除范围为 `0x000000–0x28FFFF`，未执行整片擦除。
- `program_flash` 完整回读并逐字节比较成功，输出 `Verify Operation successful.`、`Flash Operation Successful`。
- 镜像包含 FSBL、带 SW0 的 bitstream 和双模式 ELF。软件驱动和 JTAG 启动已验证，脱离 JTAG 冷启动独立验收。
- QSPI 冷启动尚未物理验收，需要断电设置 JP5 后重新上电。

## 尚未物理验证

- 耳机/音箱实际听感、模拟音频电平。
- 实际拔插 USB 后再次播放。
- 现场拨动 SW0 的运行时切换；当前 SW0=1 的启动读取已确认，来回切换通过调试器请求验证。
- 脱离 JTAG 的 SD/QSPI 冷启动。
- Falcosoft 和 Drumstick 的播放器界面兼容性。

数字波形、Windows 枚举与成功构建不替代上述物理验证。正式 SD/QSPI 镜像使用 `build/usb_midi/opl3_dual.bit`，不包含 ILA。
