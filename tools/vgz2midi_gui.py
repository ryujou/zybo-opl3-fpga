# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop interface for the pure-Python OPL VGM/VGZ converter."""
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from vgz2midi import ConversionCancelled, ROOT, convert_file, find_inputs


class ConversionWorker(QThread):
    started_file = Signal(int, str)
    advanced = Signal(int, int)
    converted = Signal(int, object)
    failed = Signal(int, str)
    cancelled_file = Signal(int)
    batch_done = Signal(int, int, bool)

    def __init__(self, files, output, parent=None):
        super().__init__(parent)
        self.files, self.output = files, output

    def run(self):
        successes = failures = 0
        for index, (source, relative) in enumerate(self.files):
            if self.isInterruptionRequested():
                break
            self.started_file.emit(index, str(relative))

            def progress(fraction):
                self.advanced.emit(index, round(fraction * 1000))
                return not self.isInterruptionRequested()

            try:
                result = convert_file(source, self.output / relative, progress)
            except ConversionCancelled:
                self.cancelled_file.emit(index)
                break
            except Exception as error:
                # This is the worker/UI boundary: report the error for this file
                # and keep the rest of the explicitly selected batch usable.
                failures += 1
                self.failed.emit(index, f"{type(error).__name__}: {error}")
            else:
                successes += 1
                self.converted.emit(index, result)
        self.batch_done.emit(successes, failures, self.isInterruptionRequested())


class ConverterWindow(QMainWindow):
    def __init__(self, load_default=True):
        super().__init__()
        self.files = []
        self.worker = None
        self.close_pending = False
        self.setWindowTitle("VGM → MIDI · OPL 转换工具")
        self.resize(1060, 780)
        self.setMinimumSize(820, 650)
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("VGM → MIDI")
        title.setObjectName("title")
        titles.addWidget(title)
        subtitle = QLabel("把 OPL 音乐转换为标准 MIDI，交给你喜欢的播放器。")
        subtitle.setObjectName("muted")
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        badge = QLabel("纯 Python  /  OPL2 · OPL3")
        badge.setObjectName("badge")
        heading.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        output_card = QFrame()
        output_card.setObjectName("card")
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(16, 12, 16, 12)
        output_label = QLabel("MIDI 输出目录")
        output_label.setObjectName("sectionLabel")
        output_layout.addWidget(output_label)
        output_row = QHBoxLayout()
        self.output = QLineEdit(str(ROOT / "midi/converted"))
        self.output.setMinimumHeight(36)
        self.browse_output = QPushButton("选择目录…")
        self.browse_output.clicked.connect(self.choose_output)
        self.open_output = QPushButton("打开输出")
        self.open_output.clicked.connect(self.show_output)
        output_row.addWidget(self.output, 1)
        output_row.addWidget(self.browse_output)
        output_row.addWidget(self.open_output)
        output_layout.addLayout(output_row)
        hint = QLabel("保留输入目录结构 · 同名 MIDI 会覆盖")
        hint.setObjectName("muted")
        output_layout.addWidget(hint)
        layout.addWidget(output_card)

        actions = QHBoxLayout()
        self.count_label = QLabel("转换队列 · 0 个文件")
        self.count_label.setObjectName("sectionLabel")
        actions.addWidget(self.count_label)
        actions.addStretch()
        self.add_files_button = QPushButton("添加文件…")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button = QPushButton("添加文件夹…")
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.clear_button = QPushButton("清空")
        self.clear_button.clicked.connect(self.clear_files)
        for button in (self.add_files_button, self.add_folder_button, self.clear_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("文件", "芯片", "时长", "音符", "状态"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 75), (2, 95), (3, 80), (4, 115)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        self.status = QLabel("添加 VGM/VGZ 文件或文件夹后开始转换。")
        self.status.setObjectName("sectionLabel")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setFixedHeight(90)
        self.log.setPlaceholderText("转换结果和失败原因会显示在这里。")
        layout.addWidget(self.log)

        footer = QHBoxLayout()
        note = QLabel("OPL2 / OPL3 2-op · DRO2MIDI 匹配规则 · FM → GM 为近似转换。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        self.cancel_button = QPushButton("停止转换")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        footer.addWidget(self.cancel_button)
        self.start_button = QPushButton("开始转换")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumWidth(135)
        self.start_button.clicked.connect(self.start)
        footer.addWidget(self.start_button)
        layout.addLayout(footer)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f6f9; color: #243247;
                font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; }
            QLabel#title { font-size: 30px; font-weight: 700; color: #17283d; }
            QLabel#muted { color: #67768a; font-size: 12px; }
            QLabel#sectionLabel { font-weight: 600; }
            QLabel#badge { background: #e4eff2; color: #286470;
                padding: 8px 12px; border-radius: 7px; font-size: 12px; }
            QFrame#card { background: white; border: 1px solid #dfe5ed; border-radius: 10px; }
            QFrame#card QLabel { background: transparent; }
            QLineEdit, QPlainTextEdit { background: white; border: 1px solid #dce3ec;
                border-radius: 6px; padding: 7px; selection-background-color: #dcebf5; }
            QLineEdit:focus { border-color: #448da1; }
            QPlainTextEdit { color: #536477; font-size: 12px; }
            QPushButton { background: white; border: 1px solid #d8e1eb; border-radius: 6px;
                padding: 8px 13px; font-weight: 500; }
            QPushButton:hover { background: #eaf0f6; border-color: #a9bdcc; }
            QPushButton:disabled { color: #a5afbc; background: #f0f3f6; border-color: #e1e7ef; }
            QPushButton#primary { background: #23748b; color: white; border-color: #23748b; }
            QPushButton#primary:hover { background: #1b6075; }
            QPushButton#primary:disabled { background: #9cbcc5; border-color: #9cbcc5; }
            QTableWidget { background: white; alternate-background-color: #f8fafc;
                border: 1px solid #dfe5ed; border-radius: 7px;
                selection-background-color: #e3eff5; selection-color: #243247; }
            QHeaderView::section { background: #edf1f6; color: #617186; border: none;
                padding: 10px 8px; text-align: left; font-weight: 600; }
            QTableWidget::item { padding: 5px 8px; }
            QProgressBar { border: none; border-radius: 3px; background: #dfe7ef; }
            QProgressBar::chunk { background: #2991a2; border-radius: 3px; }
        """)
        if load_default and (ROOT / "midi").is_dir():
            self.add_source(ROOT / "midi")
        self.start_button.setEnabled(bool(self.files))

    def add_source(self, source):
        existing = {str(path.resolve()).casefold() for path, _ in self.files}
        inputs = find_inputs(source)
        for path, relative in inputs:
            identity = str(path.resolve()).casefold()
            if identity in existing:
                continue
            existing.add(identity)
            row = self.table.rowCount()
            self.files.append((path, relative))
            self.table.insertRow(row)
            for column, text in enumerate((str(relative.with_suffix(path.suffix)), "—", "—", "—", "待转换")):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setToolTip(str(path))
        self.count_label.setText(f"转换队列 · {len(self.files)} 个文件")
        self.start_button.setEnabled(bool(self.files))
        self.status.setText(f"已就绪 · {len(self.files)} 个文件")
        if not inputs:
            self.log.appendPlainText(f"未找到 VGM/VGZ 文件：{source}")

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 VGM/VGZ", str(ROOT / "midi"),
                                               "VGM/VGZ (*.vgm *.vgz *.VGM *.VGZ)")
        for path in files:
            self.add_source(path)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择音乐文件夹", str(ROOT / "midi"))
        if path:
            self.add_source(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择 MIDI 输出目录", self.output.text())
        if path:
            self.output.setText(path)

    def show_output(self):
        path = Path(self.output.text().strip())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        else:
            QMessageBox.information(self, "输出目录", "输出目录尚不存在，转换时会自动创建。")

    def clear_files(self):
        self.files.clear()
        self.table.setRowCount(0)
        self.count_label.setText("转换队列 · 0 个文件")
        self.status.setText("添加 VGM/VGZ 文件或文件夹后开始转换。")
        self.progress.setValue(0)
        self.start_button.setEnabled(False)
        self.log.clear()

    def set_busy(self, busy):
        for widget in (self.output, self.browse_output, self.add_files_button,
                       self.add_folder_button, self.clear_button):
            widget.setEnabled(not busy)
        self.start_button.setEnabled(not busy and bool(self.files))
        self.cancel_button.setEnabled(busy)

    def start(self):
        if self.worker is not None or not self.files:
            return
        if not self.output.text().strip():
            QMessageBox.warning(self, "输出目录", "请先指定 MIDI 输出目录。")
            return
        destinations = [str(relative).casefold() for _, relative in self.files]
        if len(set(destinations)) != len(destinations):
            QMessageBox.warning(self, "文件名冲突", "输入文件转换后的 .mid 路径重复，请分批转换到不同目录。")
            return
        self.log.clear()
        self.progress.setValue(0)
        for row in range(self.table.rowCount()):
            self.set_row_status(row, "待转换", "#67768a")
            self.table.item(row, 4).setToolTip("")
            for column in (1, 2, 3):
                self.table.item(row, column).setText("—")
        self.set_busy(True)
        self.worker = ConversionWorker(list(self.files), Path(self.output.text().strip()), self)
        self.worker.started_file.connect(self.on_started)
        self.worker.advanced.connect(self.on_progress)
        self.worker.converted.connect(self.on_converted)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled_file.connect(lambda row: self.set_row_status(row, "已取消", "#977031"))
        self.worker.batch_done.connect(self.on_done)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def set_row_status(self, row, text, color):
        item = self.table.item(row, 4)
        item.setText(text)
        item.setForeground(QColor(color))

    def on_started(self, row, name):
        self.set_row_status(row, "转换中", "#23748b")
        self.table.scrollToItem(self.table.item(row, 0))
        self.status.setText(f"正在转换 {row + 1} / {len(self.files)} · {Path(name).name}")
        self.status.setToolTip(name)

    def on_progress(self, row, progress):
        self.progress.setValue(round((row * 1000 + progress) / len(self.files)))

    def on_converted(self, row, result):
        for column, text in ((1, result.chip), (2, f"{result.duration:.2f} 秒"), (3, str(result.notes))):
            self.table.item(row, column).setText(text)
        self.set_row_status(row, "已完成", "#23826b")
        detail = f"音色近似音符 {result.approximate_notes}；通道近似分配 {result.channel_approximations}"
        self.table.item(row, 4).setToolTip(detail)
        self.log.appendPlainText(f"✓ {self.files[row][1]} · {result.notes} 音符 · {detail}")
        self.on_progress(row, 1000)

    def on_failed(self, row, error):
        self.set_row_status(row, "失败", "#bd5353")
        self.table.item(row, 4).setToolTip(error)
        self.log.appendPlainText(f"失败 {self.files[row][0]}\n  {error}")
        self.on_progress(row, 1000)

    def on_done(self, successes, failures, cancelled):
        prefix = "已停止" if cancelled else "转换完成"
        self.status.setText(f"{prefix} · 成功 {successes}，失败 {failures}，共 {len(self.files)} 个文件")
        if not cancelled:
            self.progress.setValue(1000)

    def on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        if self.close_pending:
            self.close()

    def cancel(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在停止转换…")

    def closeEvent(self, event):
        if self.worker is not None:
            self.close_pending = True
            self.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OPL VGM to MIDI")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = ConverterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
