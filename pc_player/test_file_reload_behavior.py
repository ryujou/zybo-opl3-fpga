from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from main import MainWindow


class StubThread:
    def __init__(self) -> None:
        self._running = True
        self.stop_requested = False
        self.wait_called = False

    def isRunning(self) -> bool:
        return self._running

    def request_stop(self) -> None:
        self.stop_requested = True
        self._running = False

    def wait(self) -> None:
        self.wait_called = True


def run() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    stub = StubThread()
    window.player_thread = stub
    window.progress.setValue(77)

    window._stop_active_playback_for_reload()

    assert stub.stop_requested, 'reload should stop active playback first'
    assert stub.wait_called, 'reload should wait for thread exit before switching song'
    assert window.status_label.text() == '当前状态：正在停止当前播放并加载新文件'
    assert window.progress.value() == 0
    app.processEvents()
    window.close()


if __name__ == '__main__':
    run()
    print('test_file_reload_behavior: ok')
