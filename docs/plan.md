# v1.0.0 版本基线

固定交付同一 tag 的源码、Windows EXE、BOOT.bin、bitstream 和 ELF。

| 部分 | 固定行为与验证 |
| --- | --- |
| MIDI 固件 | bank 58、固定库源码和 FPGA 后端；协议、合成与 30 分钟连续播放已验证。 |
| SW0 双模式 | 两种 USB 身份分别枚举；原始 VGM/VGZ 上传、暂停/停止、两首整曲播放和调试器触发切换已验证。 |
| Windows 播放器 | 单文件 EXE 包含 Python、Qt 和 libusb；原始寄存器与采样时间保持。 |
| 可选转换器 | Python CLI / PySide6 GUI，OPL 2-op 到标准 MIDI 的近似映射。 |
| 启动镜像 | 匹配 FSBL、SW0 bitstream 和双模式 ELF；QSPI 写入与完整回读通过。 |

SD/QSPI 冷启动、实际 USB 插拔、现场拨动开关和模拟音频验收状态见 [progress.md](progress.md)；构建和连接步骤见 [project.md](project.md)。
