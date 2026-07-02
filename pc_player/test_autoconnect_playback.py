from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

import main
from midi_loader import LoadedMidi


class StubSignal:
    def connect(self, _slot) -> None:
        return None


class StubThread:
    def __init__(self, device_key: str, song: LoadedMidi) -> None:
        self.device_key = device_key
        self.song = song
        self.status_changed = StubSignal()
        self.progress_changed = StubSignal()
        self.error_occurred = StubSignal()
        self.finished = StubSignal()
        self.connected = StubSignal()
        self.started = False

    def start(self) -> None:
        self.started = True

    def isRunning(self) -> bool:
        return False


class ConnectRecorder:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    def __call__(self, *, show_dialog: bool) -> bool:
        self.calls.append(show_dialog)
        return True


def run() -> None:
    app = QApplication.instance() or QApplication([])
    window = main.MainWindow()
    recorder = ConnectRecorder()

    original_thread = main.PlayerThread
    try:
        main.PlayerThread = StubThread
        window._connect_device = recorder
        window.device_key = 'dev0'
        window.device_label.setText('stub-device')
        window.song = LoadedMidi(events=[], total_us=0, title='demo.mid', source_path='demo.mid', parsed_path='demo.mid')

        window.start_playback()

        assert recorder.calls == [False], 'playback should auto-connect without modal prompt first'
        assert isinstance(window.player_thread, StubThread)
        assert window.player_thread.started
        assert window.status_label.text() == '当前状态：准备播放'
    finally:
        main.PlayerThread = original_thread
        app.processEvents()
        window.close()


if __name__ == '__main__':
    run()
    print('test_autoconnect_playback: ok')
