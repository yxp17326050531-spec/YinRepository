"""PVE experiment UI, intentionally separate from capture and battle statistics."""
from datetime import datetime
import ctypes
import os
from ctypes import wintypes as W
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QPlainTextEdit, QFormLayout, QFileDialog, QMessageBox)
from afk import WindowInput, Trial, Step


class AfkDialog(QDialog):
    def __init__(self, parent=None, backend=None):
        super().__init__(parent)
        self.setWindowTitle('PVE 后台操作 · 最小化 / 锁屏试验'); self.resize(720,620)
        self.backend = None; self.registered = False; self.hotkey = False
        self.picking = False; self.trial = None; self.last_state = None
        layout = QVBoxLayout(self)
        text = QLabel('先手动进入副本并开启游戏自动战斗。按固定等待时间发送结算、再次挑战点击。\n'
                      '本版不识别结算、体力或购买弹窗，坐标可能点错；先在前台短时验证。\n'
                      '最小化、锁屏下能否生效待实测；发送成功≠游戏执行成功。睡眠后不补发点击。')
        text.setWordWrap(True); layout.addWidget(text)
        self.controls = []; self.windows = QComboBox(); self.controls.append(self.windows)
        bar = QHBoxLayout(); bar.addWidget(self.windows,1)
        self.refresh = QPushButton('刷新游戏窗口'); self.refresh.clicked.connect(self.refresh_windows)
        self.controls.append(self.refresh); bar.addWidget(self.refresh); layout.addLayout(bar)
        form = QFormLayout(); layout.addLayout(form); self.steps = []
        for name, wait in [('结算 / 继续',180), ('再次挑战',3)]:
            row = QHBoxLayout(); x = self.spin(-1,32767,-1); y = self.spin(-1,32767,-1)
            delay = self.spin(1,3600,wait); pick = QPushButton('5秒后取鼠标位置')
            pick.clicked.connect(lambda checked=False, x=x, y=y:self.pick(x,y))
            for item in [QLabel('X'),x,QLabel('Y'),y,QLabel('点击前等待(秒)'),delay,pick]:row.addWidget(item)
            form.addRow(name,row); self.steps.append((name,x,y,delay)); self.controls.extend([x,y,delay,pick])
        self.rounds = self.spin(1,20,3); self.limit = self.spin(1,120,10)
        form.addRow('试验轮数（不是已完成副本数）',self.rounds); form.addRow('总时限（分钟）',self.limit)
        self.controls.extend([self.rounds,self.limit])
        self.start = QPushButton('开始试验'); self.start.clicked.connect(self.begin)
        self.stop_button = QPushButton('立即停止'); self.stop_button.clicked.connect(self.stop)
        export = QPushButton('导出试验记录'); export.clicked.connect(self.export)
        bar = QHBoxLayout()
        for item in [self.start,self.stop_button,export]:bar.addWidget(item)
        layout.addLayout(bar); self.state = QLabel('未运行'); layout.addWidget(self.state)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(500); layout.addWidget(self.log,1)
        self.timer = QTimer(self); self.timer.setInterval(250); self.timer.timeout.connect(self.tick)
        self.pick_timer = QTimer(self); self.pick_timer.setSingleShot(True); self.pick_timer.timeout.connect(self.finish_pick)
        try:
            self.backend = backend or WindowInput()
            self.trial = Trial(self.backend, report=self.report)
            self.refresh_windows()
        except Exception as exc:self.report(str(exc)); self.start.setEnabled(False)
        self.windows.currentIndexChanged.connect(self.reset_points)

    @staticmethod
    def spin(low, high, value):
        item = QSpinBox(); item.setRange(low,high); item.setValue(value); return item

    def report(self, message):
        self.log.appendPlainText(f'{datetime.now():%H:%M:%S} {message}')

    def reset_points(self):
        for _,x,y,_ in self.steps:x.setValue(-1); y.setValue(-1)

    def refresh_windows(self):
        if not self.backend:return
        self.windows.clear(); self.reset_points()
        try:
            for target in self.backend.windows():
                self.windows.addItem(f'伊瑟 · 进程 {target[1][0]} · 窗口 {target[0]} · {target[2][0]}×{target[2][1]}',target)
            if not self.windows.count():self.report('未找到可访问的伊瑟游戏窗口，请启动游戏后刷新')
        except Exception as exc:self.report(f'检测失败：{exc}')

    def enable_controls(self, enabled):
        for control in self.controls:control.setEnabled(enabled)
        self.start.setEnabled(enabled and self.backend is not None)

    def pick(self, x, y):
        target = self.windows.currentData()
        if not target:return
        self.pick_target = target; self.pick_fields = (x,y); self.picking = True
        self.enable_controls(False); self.report('请在5秒内把鼠标停在游戏按钮中央，不用点击')
        self.pick_timer.start(5000)

    def finish_pick(self):
        if not self.picking:return
        self.pick_timer.stop()
        try:
            point = self.backend.point(self.pick_target)
            for widget,value in zip(self.pick_fields,point):widget.setValue(value)
            self.report(f'已记录客户区位置 {point}')
        except Exception as exc:self.report(f'取点失败：{exc}')
        self.picking = False; self.enable_controls(True)

    def begin(self):
        try:
            target = self.windows.currentData()
            if target is None:raise ValueError('请先选择游戏窗口')
            steps = [Step(name,(x.value(),y.value()),delay.value()) for name,x,y,delay in self.steps]
            self.trial.start(target,steps,self.rounds.value(),self.limit.value()*60)
            self.enable_controls(False); self.last_state = None; self.timer.start()
        except Exception as exc:QMessageBox.warning(self,'无法开始',str(exc))

    def tick(self):
        self.trial.tick()
        if not self.trial.running:
            self.timer.stop(); self.enable_controls(True); self.state.setText('已停止'); return
        try:
            self.backend.validate(self.trial.target)
            minimized = bool(self.backend.user.IsIconic(self.trial.target[0]))
            if minimized != self.last_state:
                self.report('游戏窗口：' + ('已最小化' if minimized else '未最小化')); self.last_state = minimized
            remaining = max(0,int(self.trial.due-self.trial.clock()))
            self.state.setText(f'已发送 {self.trial.completed} 轮；下一步 {remaining} 秒后；执行结果待游戏确认')
        except Exception as exc:self.trial.stop(str(exc))

    def stop(self):
        self.pick_timer.stop(); self.picking = False
        if self.trial:self.trial.stop()
        self.timer.stop(); self.enable_controls(True); self.state.setText('已停止')

    def showEvent(self,event):
        super().showEvent(event)
        if self.backend and hasattr(self.backend,'wts'):
            hwnd = int(self.winId())
            if not self.registered:self.registered = bool(self.backend.wts.WTSRegisterSessionNotification(hwnd,0))
            if not self.hotkey:self.hotkey = bool(self.backend.user.RegisterHotKey(hwnd,0x5045,0x4003,0x77))
            self.report('Ctrl+Alt+F8 可停止试验（锁屏时请依靠次数和总时限）' if self.hotkey else '停止热键注册失败，请使用停止按钮和总时限')
            if not self.registered:self.report('锁屏通知注册失败，无法记录锁屏状态')

    def nativeEvent(self,event_type,message):
        if os.name != 'nt':return super().nativeEvent(event_type,message)
        msg = W.MSG.from_address(int(message))
        if msg.message == 0x312 and msg.wParam == 0x5045:
            self.stop(); return True,0
        if msg.message == 0x2B1 and msg.wParam in (7,8):
            self.report('Windows：已锁屏' if msg.wParam == 7 else 'Windows：已解锁')
        return super().nativeEvent(event_type,message)

    def shutdown(self):
        self.stop()
        if self.backend:
            hwnd = int(self.winId())
            if self.registered:self.backend.wts.WTSUnRegisterSessionNotification(hwnd)
            if self.hotkey:self.backend.user.UnregisterHotKey(hwnd,0x5045)
        self.registered = self.hotkey = False

    def closeEvent(self,event):
        self.shutdown(); super().closeEvent(event)

    def done(self,result):
        self.shutdown(); super().done(result)

    def export(self):
        path,_ = QFileDialog.getSaveFileName(self,'保存试验记录','pve-trial.txt','文本 (*.txt)')
        if path:
            try:
                with open(path,'w',encoding='utf-8') as output:output.write(self.log.toPlainText())
            except OSError as exc:QMessageBox.warning(self,'保存失败',str(exc))
