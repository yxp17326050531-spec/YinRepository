"""Background release checks and user-confirmed EXE updates."""
from datetime import datetime
import sys

from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

import exe_updater as updater


class UpdateTask(QThread):
    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.callback()
        except Exception as exc:
            self.error = str(exc)


class UpdateController(QObject):
    def __init__(self, window, layout, version):
        super().__init__(window)
        self.window = window
        self.version = version
        self.task = None
        self.release = None
        self.status = QLabel('程序更新来自 GitHub 官方发行页。')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.button = QPushButton('检查程序更新')
        layout.addWidget(self.button)
        self.button.clicked.connect(self.clicked)
        self.browser_button = QPushButton('打开 GitHub 发行页')
        self.browser_button.clicked.connect(self.open_release_page)
        layout.addWidget(self.browser_button)
        self.browser_button.hide()
        self.startup_check = QTimer(self)
        self.startup_check.setSingleShot(True)
        self.startup_check.timeout.connect(self.check)
        if updater.install_root() is not None and '--smoke-test' not in sys.argv:
            self.startup_check.start(3000)

    def start(self, callback, success):
        if self.task is not None:
            return
        self.button.setEnabled(False)
        self.task = UpdateTask(callback, self)
        self.on_success = success
        self.task.finished.connect(self.finished)
        self.task.start()

    @Slot()
    def finished(self):
        task = self.task
        success = self.on_success
        self.task = self.on_success = None
        self.button.setEnabled(True)
        task.deleteLater()
        if task.error is None:
            success(task.result)
        else:
            self.failed(task.error)

    def clicked(self):
        self.startup_check.stop()
        if self.release:
            self.offer_update()
        else:
            self.check()

    def check(self):
        self.status.setText('正在检查 GitHub 发行版…')
        self.start(self.check_release, self.checked)

    def check_release(self):
        root = updater.install_root()
        if root is not None:
            try:
                updater.clean_completed_update(root)
            except (OSError, ValueError):
                # A pending cleanup can be retried without blocking release checks.
                self.window.archive.logger.exception('update cleanup')
        return updater.check(self.version)

    def checked(self, release):
        self.release = release
        self.browser_button.setVisible(bool(release))
        if release:
            self.status.setText('发现新版 ' + release['version'] + '\n' + release['notes'][:1200])
            self.button.setText('下载并安装 ' + release['version'])
            if updater.install_root() is not None:
                self.offer_update()
        else:
            self.status.setText('当前已是此渠道最新版本。')
            self.button.setText('检查程序更新')

    def offer_update(self):
        root = updater.install_root()
        if root is None:
            self.status.setText('源码版请运行 update.cmd。')
            return
        release = self.release
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle('发现新版本')
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(f"当前版本 {self.version}\n可更新至 {release['version']}")
        dialog.setInformativeText('下载并校验完成后，助手会备份数据库、退出并安装新版。')
        if release['notes']:
            dialog.setDetailedText(release['notes'])
        install = dialog.addButton('立即更新', QMessageBox.ButtonRole.AcceptRole)
        later = dialog.addButton('稍后', QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(later)
        dialog.setEscapeButton(later)
        dialog.exec()
        if dialog.clickedButton() == install:
            self.status.setText('正在下载并校验更新，请保持程序开启…')
            self.start(lambda: updater.prepare(release, root), self.ready)

    def ready(self, task):
        try:
            archive = self.window.archive
            target = archive.directory / 'backups' / ('before-update-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
            target.parent.mkdir(exist_ok=True)
            archive.backup(target)
            updater.launch_worker(task, updater.install_root())
            self.status.setText('校验与数据库备份完成，正在退出并安装…')
            self.button.setEnabled(False)
            QTimer.singleShot(200, self.window.close)
        except Exception as exc:
            self.failed(str(exc))

    def failed(self, message):
        self.browser_button.show()
        self.status.setText('更新未完成。可稍后重试，或打开 GitHub 发行页手动下载。\n' + message)

    def open_release_page(self):
        version = self.release['version'] if self.release else None
        QDesktopServices.openUrl(QUrl(updater.release_page(version)))
