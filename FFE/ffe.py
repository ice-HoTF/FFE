#!/usr/bin/env python3
import os
import sys
import shutil
from pathlib import Path
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QProgressBar,
    QMessageBox,
)

EXCLUDED_DIRS = {".git", "build", ".gradle", ".idea", ".kotlin"}


class ExportWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, source, dest):
        super().__init__()
        self.source = Path(source).resolve()
        self.dest = Path(dest).resolve()

    def run(self):
        try:
            files = []
            for root, dirs, names in os.walk(self.source):
                root_path = Path(root)
                dirs[:] = [
                    d for d in dirs
                    if d not in EXCLUDED_DIRS and (root_path / d).resolve() != self.dest
                ]
                for name in names:
                    files.append(root_path / name)
            files.sort()
            self.dest.mkdir(parents=True, exist_ok=True)
            total = len(files)
            used = set()
            for i, f in enumerate(files, 1):
                rel = f.relative_to(self.source)
                flat = "_".join(rel.parts)
                candidate = flat
                n = 2
                while candidate in used:
                    stem, dot, ext = flat.rpartition(".")
                    candidate = f"{stem}_{n}.{ext}" if dot and stem else f"{flat}_{n}"
                    n += 1
                used.add(candidate)
                shutil.copy2(f, self.dest / candidate)
                self.progress.emit(i, total)
            self.finished_ok.emit(total)
        except Exception as e:
            self.failed.emit(str(e))


class DropZone(QLabel):
    dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__("Drag folder here")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(140)
        self.setWordWrap(True)
        self.setAcceptDrops(True)
        self.set_idle()

    def set_idle(self):
        self.setStyleSheet(
            "QLabel { border: 2px dashed palette(mid); border-radius: 8px; font-size: 14px; padding: 10px; }"
        )

    def set_hover(self):
        self.setStyleSheet(
            "QLabel { border: 2px dashed palette(highlight); border-radius: 8px; font-size: 14px; padding: 10px; }"
        )

    def first_dir(self, event):
        if not event.mimeData().hasUrls():
            return None
        path = event.mimeData().urls()[0].toLocalFile()
        return path if os.path.isdir(path) else None

    def dragEnterEvent(self, event):
        if self.first_dir(event):
            event.acceptProposedAction()
            self.set_hover()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.first_dir(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.set_idle()

    def dropEvent(self, event):
        self.set_idle()
        path = self.first_dir(event)
        if path:
            event.acceptProposedAction()
            self.dropped.emit(path)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFE - Folder File Exporter")
        self.resize(560, 360)
        self.worker = None

        self.drop = DropZone()
        self.drop.dropped.connect(self.set_source)

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Any folder")
        source_btn = QPushButton("Browse…")
        source_btn.clicked.connect(self.browse_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_edit)
        source_row.addWidget(source_btn)

        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Export folder")
        dest_btn = QPushButton("Browse…")
        dest_btn.clicked.connect(self.browse_dest)
        dest_row = QHBoxLayout()
        dest_row.addWidget(self.dest_edit)
        dest_row.addWidget(dest_btn)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status = QLabel("Ready")

        self.export_btn = QPushButton("Export")
        self.export_btn.setMinimumHeight(36)
        self.export_btn.clicked.connect(self.export)

        layout = QVBoxLayout(self)
        layout.addWidget(self.drop)
        layout.addWidget(QLabel("Source:"))
        layout.addLayout(source_row)
        layout.addWidget(QLabel("Export to:"))
        layout.addLayout(dest_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.export_btn)

    def set_source(self, path):
        self.source_edit.setText(path)
        self.drop.setText(f"Project:\n{path}")

    def browse_source(self):
        path = QFileDialog.getExistingDirectory(self, "Select folder", str(Path.home()))
        if path:
            self.set_source(path)

    def browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select export folder", str(Path.home()))
        if path:
            self.dest_edit.setText(path)

    def export(self):
        src = self.source_edit.text().strip()
        dst = self.dest_edit.text().strip()
        if not src or not os.path.isdir(src):
            QMessageBox.warning(self, "Error", "Select a valid folder.")
            return
        if not dst:
            QMessageBox.warning(self, "Error", "Select an export folder.")
            return
        if Path(dst).resolve() == Path(src).resolve():
            QMessageBox.warning(self, "Error", "Export folder cannot be the project folder.")
            return
        self.export_btn.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText("Scanning…")
        self.worker = ExportWorker(src, dst)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_ok.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_progress(self, i, total):
        self.progress.setMaximum(total)
        self.progress.setValue(i)
        self.status.setText(f"Copying {i} / {total}")

    def on_done(self, total):
        self.export_btn.setEnabled(True)
        self.status.setText(f"Done. {total} files exported.")
        QMessageBox.information(self, "Done", f"{total} files exported to:\n{self.dest_edit.text()}")

    def on_failed(self, msg):
        self.export_btn.setEnabled(True)
        self.status.setText("Failed.")
        QMessageBox.critical(self, "Error", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Folder File Exporter")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
