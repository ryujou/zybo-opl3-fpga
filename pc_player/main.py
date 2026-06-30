from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import serial.tools.list_ports

from midi_loader import LoadedMidi, load_midi_file
from protocol import ProtocolError, ZyboTransport
from song_builder import BuiltSong, build_preloaded_song
from vgm_loader import LoadedVgm, load_vgm_file


LoadedSong = LoadedMidi | LoadedVgm


class PlayerThread(QThread):
    status_changed = Signal(str)
    progress_changed = Signal(int)
    error_occurred = Signal(str)
    playback_finished = Signal()
    connected = Signal(str)

    def __init__(self, port: str, song: LoadedSong) -> None:
        super().__init__()
        self.port = port
        self.song = song

    def run(self) -> None:
        transport = ZyboTransport(self.port)

        try:
            self.status_changed.emit("正在构建 OPL 事件")
            built_song: BuiltSong = build_preloaded_song(self.song)
            if not built_song.data:
                raise ProtocolError("没有生成任何可播放的 OPL 事件")

            self.progress_changed.emit(5)
            hello = transport.open()
            self.connected.emit(
                f"已连接，协议 {hello.version_major}.{hello.version_minor}，板端缓存 {hello.preload_capacity // 1024} KB"
            )

            if hello.preload_capacity and len(built_song.data) > hello.preload_capacity:
                raise ProtocolError(
                    f"曲目转换后为 {len(built_song.data)} 字节，超过板端缓存上限 {hello.preload_capacity} 字节"
                )

            self.status_changed.emit("正在上传到板端内存")
            transport.upload_song(built_song.data)
            self.progress_changed.emit(20)

            self.status_changed.emit("板端本地播放中")
            transport.timeout = max(10.0, (built_song.total_delay_us / 1_000_000.0) + 10.0)
            transport.play_buffered()

            self.progress_changed.emit(100)
            self.status_changed.emit("播放完成")
            self.playback_finished.emit()
        except (ProtocolError, OSError, ValueError) as exc:
            self.error_occurred.emit(str(exc))
        finally:
            transport.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zybo OPL3 复古音乐播放器")
        self.resize(780, 360)

        self.song: Optional[LoadedSong] = None
        self.player_thread: Optional[PlayerThread] = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        conn_group = QGroupBox("连接设置")
        conn_layout = QGridLayout(conn_group)
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("刷新串口")
        self.connect_button = QPushButton("连接测试")
        self.connect_status = QLabel("未连接")
        conn_layout.addWidget(QLabel("串口"), 0, 0)
        conn_layout.addWidget(self.port_combo, 0, 1)
        conn_layout.addWidget(self.refresh_button, 0, 2)
        conn_layout.addWidget(self.connect_button, 0, 3)
        conn_layout.addWidget(QLabel("状态"), 1, 0)
        conn_layout.addWidget(self.connect_status, 1, 1, 1, 3)

        file_group = QGroupBox("曲目文件")
        file_layout = QHBoxLayout(file_group)
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_button = QPushButton("选择文件")
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(self.file_button)

        playback_group = QGroupBox("播放控制")
        playback_layout = QGridLayout(playback_group)
        self.play_button = QPushButton("播放")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        self.restart_button = QPushButton("重新开始")
        self.song_label = QLabel("当前曲目：未选择")
        self.status_label = QLabel("当前状态：未连接")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        playback_layout.addWidget(self.play_button, 0, 0)
        playback_layout.addWidget(self.pause_button, 0, 1)
        playback_layout.addWidget(self.stop_button, 0, 2)
        playback_layout.addWidget(self.restart_button, 0, 3)
        playback_layout.addWidget(self.song_label, 1, 0, 1, 4)
        playback_layout.addWidget(self.status_label, 2, 0, 1, 4)
        playback_layout.addWidget(self.progress, 3, 0, 1, 4)

        layout.addWidget(conn_group)
        layout.addWidget(file_group)
        layout.addWidget(playback_group)
        layout.addStretch(1)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.file_button.clicked.connect(self.select_file)
        self.connect_button.clicked.connect(self.test_connection)
        self.play_button.clicked.connect(self.start_playback)
        self.pause_button.clicked.connect(self.pause_playback)
        self.stop_button.clicked.connect(self.stop_playback)
        self.restart_button.clicked.connect(self.restart_playback)

        self.refresh_ports()
        self._set_buttons(is_playing=False)

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        for port in serial.tools.list_ports.comports():
            self.port_combo.addItem(port.device)
        index = self.port_combo.findText(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def select_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择音乐文件",
            str(Path("midi").resolve()),
            "支持的文件 (*.mid *.midi *.vgm *.vgz)",
        )
        if not path:
            return

        try:
            self.song = load_song(path)
        except Exception as exc:
            QMessageBox.critical(self, "加载失败", f"无法打开音乐文件：{exc}")
            return

        self.file_edit.setText(path)
        self.song_label.setText(f"当前曲目：{self.song.title}")
        self.status_label.setText("当前状态：已加载")
        self.progress.setValue(0)
        self._set_buttons(is_playing=False)

    def test_connection(self) -> None:
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "串口未选择", "请先选择串口。")
            return

        transport = ZyboTransport(port)
        try:
            hello = transport.open()
            self.connect_status.setText(
                f"已连接，协议 {hello.version_major}.{hello.version_minor}，板端缓存 {hello.preload_capacity // 1024} KB"
            )
            self.status_label.setText("当前状态：已连接")
        except Exception as exc:
            QMessageBox.critical(self, "连接失败", f"无法连接板子：{exc}")
            self.connect_status.setText("错误")
        finally:
            transport.close()

    def start_playback(self) -> None:
        if self.player_thread is not None and self.player_thread.isRunning():
            return
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "串口未选择", "请先选择串口。")
            return
        if self.song is None:
            QMessageBox.warning(self, "文件未选择", "请先选择一个音乐文件。")
            return

        self.player_thread = PlayerThread(port, self.song)
        self.player_thread.status_changed.connect(self.on_status_changed)
        self.player_thread.progress_changed.connect(self.progress.setValue)
        self.player_thread.error_occurred.connect(self.on_error)
        self.player_thread.playback_finished.connect(self.on_finished)
        self.player_thread.connected.connect(self.on_connected)
        self.player_thread.start()
        self.status_label.setText("当前状态：准备播放")
        self._set_buttons(is_playing=True)

    def pause_playback(self) -> None:
        QMessageBox.information(self, "暂停未实现", "当前为板端阻塞式本地播放模式，暂不支持暂停。")

    def stop_playback(self) -> None:
        QMessageBox.information(self, "停止未实现", "当前为板端阻塞式本地播放模式，播放开始后暂不支持中途停止。")

    def restart_playback(self) -> None:
        self.progress.setValue(0)
        self.start_playback()

    def on_status_changed(self, text: str) -> None:
        self.status_label.setText(f"当前状态：{text}")

    def on_connected(self, text: str) -> None:
        self.connect_status.setText(text)

    def on_error(self, text: str) -> None:
        self.player_thread = None
        self.status_label.setText("当前状态：错误")
        self._set_buttons(is_playing=False)
        QMessageBox.critical(self, "播放失败", text)

    def on_finished(self) -> None:
        self.player_thread = None
        self._set_buttons(is_playing=False)

    def _set_buttons(self, *, is_playing: bool) -> None:
        has_song = self.song is not None
        self.play_button.setEnabled(has_song and not is_playing)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.restart_button.setEnabled(has_song and not is_playing)


def load_song(path: str) -> LoadedSong:
    suffix = Path(path).suffix.lower()
    if suffix in (".mid", ".midi"):
        return load_midi_file(path)
    if suffix in (".vgm", ".vgz"):
        return load_vgm_file(path)
    raise ValueError(f"不支持的文件类型: {suffix}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Zybo OPL3 复古音乐播放器")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
