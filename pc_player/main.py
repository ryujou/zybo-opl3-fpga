from __future__ import annotations

import sys
import time
from pathlib import Path
from threading import Lock
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

from midi_loader import LoadedMidi, load_midi_file
from protocol import ProtocolError, ZyboTransport, list_usb_devices
from song_builder import BuiltSong, build_preloaded_song
from vgm_loader import LoadedVgm, load_vgm_file


LoadedSong = LoadedMidi | LoadedVgm


class PlayerThread(QThread):
    status_changed = Signal(str)
    progress_changed = Signal(int)
    error_occurred = Signal(str)
    playback_finished = Signal()
    connected = Signal(str)

    def __init__(self, device_key: str, song: LoadedSong) -> None:
        super().__init__()
        self.device_key = device_key
        self.song = song
        self._lock = Lock()
        self._stop_requested = False
        self._restart_requested = False
        self._pause_requested = False

    def request_pause(self, paused: bool) -> None:
        with self._lock:
            self._pause_requested = paused

    def request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True

    def request_restart(self) -> None:
        with self._lock:
            self._restart_requested = True

    def _consume_controls(self) -> tuple[bool, bool, bool]:
        with self._lock:
            stop_requested = self._stop_requested
            restart_requested = self._restart_requested
            pause_requested = self._pause_requested
            self._stop_requested = False
            self._restart_requested = False
        return stop_requested, restart_requested, pause_requested

    def run(self) -> None:
        transport = ZyboTransport(self.device_key)

        try:
            self.status_changed.emit("正在构建 OPL 事件")
            built_song: BuiltSong = build_preloaded_song(self.song)
            if not built_song.data:
                raise ProtocolError("没有生成任何可播放的 OPL 事件")

            self.status_changed.emit(f"正在构建 OPL 事件：{built_song.backend_name}")
            if built_song.diagnostic:
                print(built_song.diagnostic)

            self.progress_changed.emit(5)
            hello = transport.open()
            self.connected.emit(
                f"已连接，协议 {hello.version_major}.{hello.version_minor}，板端缓冲 {hello.preload_capacity // 1024} KB"
            )

            if hello.preload_capacity and len(built_song.data) > hello.preload_capacity:
                raise ProtocolError(
                    f"曲目转换后为 {len(built_song.data)} 字节，超过板端缓冲上限 {hello.preload_capacity} 字节"
                )

            self.status_changed.emit("正在上传到板端内存")
            transport.upload_song(built_song.data)
            self.progress_changed.emit(20)

            self.status_changed.emit("板端本地播放中")
            transport.play_buffered()
            self._monitor_playback(transport, built_song.total_delay_us)
        except (ProtocolError, OSError, ValueError) as exc:
            self.error_occurred.emit(str(exc))
        finally:
            transport.close()
            self.playback_finished.emit()

    def _monitor_playback(self, transport: ZyboTransport, total_delay_us: int) -> None:
        total_seconds = max(total_delay_us / 1_000_000.0, 0.0)
        started_at = time.monotonic()
        paused_at: float | None = None
        paused_accumulated = 0.0
        is_paused = False
        last_progress = 20

        while True:
            stop_requested, restart_requested, pause_requested = self._consume_controls()

            if stop_requested:
                transport.stop()
                self.progress_changed.emit(0)
                self.status_changed.emit("播放已停止")
                return

            if restart_requested:
                transport.stop()
                transport.play_buffered()
                started_at = time.monotonic()
                paused_at = None
                paused_accumulated = 0.0
                is_paused = False
                last_progress = 20
                self.progress_changed.emit(20)
                self.status_changed.emit("已重新开始播放")
                continue

            if pause_requested != is_paused:
                if pause_requested:
                    transport.pause_buffered()
                    paused_at = time.monotonic()
                    is_paused = True
                    self.status_changed.emit("已暂停")
                else:
                    transport.resume_buffered()
                    if paused_at is not None:
                        paused_accumulated += time.monotonic() - paused_at
                    paused_at = None
                    is_paused = False
                    self.status_changed.emit("板端本地播放中")

            status = transport.query_status()
            if not status.playing:
                self.progress_changed.emit(100)
                self.status_changed.emit("播放完成")
                return

            if total_seconds > 0 and not is_paused:
                elapsed = time.monotonic() - started_at - paused_accumulated
                progress = min(99, max(20, int(20 + (elapsed / total_seconds) * 80)))
                if progress != last_progress:
                    self.progress_changed.emit(progress)
                    last_progress = progress

            time.sleep(0.1)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zybo OPL3 复古音乐播放器")
        self.resize(820, 380)

        self.song: Optional[LoadedSong] = None
        self.player_thread: Optional[PlayerThread] = None
        self.is_paused = False

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        conn_group = QGroupBox("连接设置")
        conn_layout = QGridLayout(conn_group)
        self.device_combo = QComboBox()
        self.refresh_button = QPushButton("刷新设备")
        self.connect_button = QPushButton("连接测试")
        self.connect_status = QLabel("未连接")
        conn_layout.addWidget(QLabel("USB 设备"), 0, 0)
        conn_layout.addWidget(self.device_combo, 0, 1)
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

        self.refresh_button.clicked.connect(self.refresh_devices)
        self.file_button.clicked.connect(self.select_file)
        self.connect_button.clicked.connect(self.test_connection)
        self.play_button.clicked.connect(self.start_playback)
        self.pause_button.clicked.connect(self.pause_playback)
        self.stop_button.clicked.connect(self.stop_playback)
        self.restart_button.clicked.connect(self.restart_playback)

        self.refresh_devices()
        self._set_buttons(is_playing=False)

    def refresh_devices(self) -> None:
        current_key = self.device_combo.currentData()
        self.device_combo.clear()
        for device in list_usb_devices():
            self.device_combo.addItem(device.label, device.key)
        if current_key is not None:
            index = self.device_combo.findData(current_key)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

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
        device_key = self.device_combo.currentData()
        if not device_key:
            QMessageBox.warning(self, "设备未选择", "请先选择 USB 设备。")
            return

        transport = ZyboTransport(device_key)
        try:
            hello = transport.open()
            self.connect_status.setText(
                f"已连接，协议 {hello.version_major}.{hello.version_minor}，板端缓冲 {hello.preload_capacity // 1024} KB"
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

        device_key = self.device_combo.currentData()
        if not device_key:
            QMessageBox.warning(self, "设备未选择", "请先选择 USB 设备。")
            return
        if self.song is None:
            QMessageBox.warning(self, "文件未选择", "请先选择一个音乐文件。")
            return

        self.player_thread = PlayerThread(device_key, self.song)
        self.player_thread.status_changed.connect(self.on_status_changed)
        self.player_thread.progress_changed.connect(self.progress.setValue)
        self.player_thread.error_occurred.connect(self.on_error)
        self.player_thread.playback_finished.connect(self.on_finished)
        self.player_thread.connected.connect(self.on_connected)
        self.player_thread.start()
        self.is_paused = False
        self.pause_button.setText("暂停")
        self.status_label.setText("当前状态：准备播放")
        self._set_buttons(is_playing=True)

    def pause_playback(self) -> None:
        if self.player_thread is None or not self.player_thread.isRunning():
            return
        self.is_paused = not self.is_paused
        self.player_thread.request_pause(self.is_paused)
        self.pause_button.setText("继续" if self.is_paused else "暂停")

    def stop_playback(self) -> None:
        if self.player_thread is None or not self.player_thread.isRunning():
            return
        self.player_thread.request_stop()

    def restart_playback(self) -> None:
        if self.player_thread is not None and self.player_thread.isRunning():
            self.is_paused = False
            self.pause_button.setText("暂停")
            self.progress.setValue(0)
            self.player_thread.request_restart()
            return
        self.progress.setValue(0)
        self.start_playback()

    def on_status_changed(self, text: str) -> None:
        self.status_label.setText(f"当前状态：{text}")

    def on_connected(self, text: str) -> None:
        self.connect_status.setText(text)

    def on_error(self, text: str) -> None:
        self.player_thread = None
        self.is_paused = False
        self.pause_button.setText("暂停")
        self.status_label.setText("当前状态：错误")
        self._set_buttons(is_playing=False)
        QMessageBox.critical(self, "播放失败", text)

    def on_finished(self) -> None:
        self.player_thread = None
        self.is_paused = False
        self.pause_button.setText("暂停")
        self._set_buttons(is_playing=False)

    def _set_buttons(self, *, is_playing: bool) -> None:
        has_song = self.song is not None
        self.play_button.setEnabled(has_song and not is_playing)
        self.pause_button.setEnabled(is_playing)
        self.stop_button.setEnabled(is_playing)
        self.restart_button.setEnabled(has_song)


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
