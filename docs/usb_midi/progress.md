# 实际验证状态

验证日期：2026-10-08。开发板为原版 Zybo / XC7Z010，Windows 11 Pro 26200。JTAG 与 USB OTG 已连接。

## 构建与主机测试

- 固定版本 libADLMIDI、FPGA 寄存器后端、bank 58 实时合成、USB-MIDI 描述符与传输、消息解析及异常静音均已完成。
- 原生测试通过：描述符长度、AC/MS 接口和 jack/端点关联，CIN/cable 检查、多事件传输、分包/超长/畸形 SysEx、CIN 0xF 字节流及 running status。
- 合成测试通过：128 音色、16 通道含鼓组、力度零 Note Off、延音、弯音、硬件声像、超额声部、GM Reset 和无输入时的时间推进。USB 解析产生的寄存器写入与相同库版本和设置的直接 API 参考结果一致。
- ARM 独立构建、Vitis `opl3_usb_midi` 构建及 Bootgen 打包通过。正式 ELF、map 和 SD 启动镜像位于 `build/usb_midi`。

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
- 当前 Python 输出为普通 SMF MIDI，共 376581 个音符、1237114 个事件，Note On/Off 配对完整；输出时长与 VGM 头部的 44.1 kHz 样本计数一致。FM 到 GM 音色及超过 15 组独立通道状态时的合并为近似转换。
- 转换核心 7 项测试通过，覆盖 bank 58 匹配、音高/音量/声像/弯音、同时间戳 Key On/Off、共享同音、18 声部、节奏鼓组、采样时间、中文路径、VGZ、取消、畸形输入与 4-op 拒绝。
- GUI 整批转换成功 86/86，转换期间窗口持续响应；逐文件失败显示、失败后继续处理、取消和控件恢复均通过实测。
- 板卡演奏验收使用的两首 MIDI 样本为《01 Introduction》98.601 秒和《02 At Doom's Gate》96.514 秒，经系统 MIDI 输出完整播放，总时长 195.1 秒、20622 条消息。板端处理/接收事件包均为 21538，队列溢出、畸形输入、USB 发送错误均为零；最大排队 398 µs、单事件处理 105 µs。
- 两首演奏的 ILA 左/右 PCM 峰值分别为 10822/10822、1598/1574。停止后左侧范围 `[-8, 0]`、右侧 `[-9, 0]`，属于现有 OPL3 核一补码符号运算的低位静音残差。
- Cynthia 使用 `Zybo OPL3 MIDI` 输出按 All Once 顺序完整播完上述两首，最后一首显示 `01m 36s 513ms`，全部 11809 个文件事件读取完毕并停止。两轮播放后板端累计处理/接收事件均为 44977，队列溢出、畸形输入和 USB 发送错误仍为零；最大排队 547 µs。
- 板卡曲目测试只覆盖这两首样本。当前 Python 转换输出完成主机侧验证，尚未复测板卡演奏。

## QSPI

- 检测到板载 Spansion S25FL128S，容量 16 MiB，页大小 256 字节、擦除扇区 64 KiB。
- `firmware/usb_midi/BOOT.bin` 共 2647492 字节，从地址 0 写入；擦除范围为 `0x000000–0x28FFFF`，未执行整片擦除。
- `program_flash` 完整回读并逐字节比较成功，输出 `Verify Operation successful.`、`Flash Operation Successful`。
- 烧录后已通过 JTAG 启动正式镜像，串口出现 `USB-MIDI ready: CAFE:4013, bank 58`；Windows 再次枚举为 `Zybo OPL3 MIDI`，状态正常。
- 当前 BOOT_MODE 读取为 0，即 JP5 仍处于 JTAG 模式；QSPI 冷启动尚未物理验证，需要断电设置 JP5 后重新上电。

## 尚未物理验证

- 耳机/音箱实际听感、模拟音频电平。
- 实际拔插 USB 后再次播放。
- 脱离 JTAG 的 SD/QSPI 冷启动。
- Falcosoft 和 Drumstick 的播放器界面兼容性。

数字波形、Windows 枚举与成功构建不替代上述物理验证。正式 SD/QSPI 镜像使用 `fpga/build/opl3.bit`，不包含 ILA。
