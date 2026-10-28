"""Background release checks and explicit user-started EXE updates."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject,QThread,Signal,QTimer
from PySide6.QtWidgets import QPushButton,QLabel,QMessageBox
import exe_updater as updater

class UpdateTask(QThread):
    done=Signal(object);failed=Signal(str)
    def __init__(self,callback,parent):super().__init__(parent);self.callback=callback
    def run(self):
        try:self.done.emit(self.callback())
        except Exception as exc:self.failed.emit(str(exc))

class UpdateController(QObject):
    def __init__(self,window,layout,version):
        super().__init__(window);self.window=window;self.version=version;self.task=None;self.release=None
        self.status=QLabel('程序更新：GitHub官方源；编号、历史与预设保存在本地，不被更新包覆盖。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.button=QPushButton('检查程序更新');layout.addWidget(self.button);self.button.clicked.connect(self.clicked)
        if updater.install_root() is not None:QTimer.singleShot(3000,self.check)
    def start(self,callback,success):
        if self.task and self.task.isRunning():return
        self.button.setEnabled(False)
        self.task=UpdateTask(callback,self);self.task.done.connect(success);self.task.failed.connect(self.failed)
        self.task.finished.connect(lambda:self.button.setEnabled(True));self.task.start()
    def clicked(self):
        if not self.release:self.check();return
        if updater.install_root() is None:
            self.status.setText('源码版请运行update.cmd；EXE版支持下载安装更新。');return
        if QMessageBox.question(self.window,'安装更新',f'安装 {self.release["version"]}？\n下载校验完成后将备份数据库、退出助手并更新。旧程序保留以便回退。')!=QMessageBox.StandardButton.Yes:return
        self.status.setText('正在下载并校验更新，请保持程序开启…')
        self.start(lambda:updater.prepare(self.release,updater.install_root()),self.ready)
    def check(self):
        self.status.setText('正在检查GitHub发行版…')
        self.start(lambda:updater.check(self.version),self.checked)
    def checked(self,release):
        self.release=release
        if release:
            self.status.setText('发现新版 '+release['version']+'\n'+release['notes'][:1200]);self.button.setText('下载并安装 '+release['version'])
        else:self.status.setText('当前已是此渠道最新版本；尚未发布的版本不会作为更新。');self.button.setText('检查程序更新')
    def ready(self,task):
        try:
            archive=self.window.archive
            target=archive.directory/'backups'/('before-update-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            target.parent.mkdir(exist_ok=True);archive.backup(target)
            updater.launch_worker(task,updater.install_root())
            self.status.setText('校验与数据库备份完成，正在退出并安装…')
            QTimer.singleShot(200,self.window.close)
        except Exception as exc:self.failed(str(exc))
    def failed(self,message):
        self.status.setText('更新未完成，当前程序和数据保留。可稍后重试。\n'+message)
