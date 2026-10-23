"""Bounded PVE window-message experiment; no foreground input or game hooks."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes as W
import os
import time

GAME_EXE = 'gameue_cpp-win64-shipping.exe'


class WindowInput:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('后台操作试验仅可在 Windows 运行')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
        signatures = [
            (self.user, 'IsWindow', [W.HWND], W.BOOL),
            (self.user, 'IsWindowVisible', [W.HWND], W.BOOL),
            (self.user, 'IsIconic', [W.HWND], W.BOOL),
            (self.user, 'GetWindowThreadProcessId', [W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
            (self.user, 'GetClientRect', [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
            (self.user, 'GetCursorPos', [ctypes.POINTER(W.POINT)], W.BOOL),
            (self.user, 'ScreenToClient', [W.HWND, ctypes.POINTER(W.POINT)], W.BOOL),
            (self.user, 'WindowFromPoint', [W.POINT], W.HWND),
            (self.user, 'GetAncestor', [W.HWND, W.UINT], W.HWND),
            (self.user, 'PostMessageW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL),
            (self.user, 'RegisterHotKey', [W.HWND, ctypes.c_int, W.UINT, W.UINT], W.BOOL),
            (self.user, 'UnregisterHotKey', [W.HWND, ctypes.c_int], W.BOOL),
            (self.kernel, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.kernel, 'CloseHandle', [W.HANDLE], W.BOOL),
            (self.kernel, 'QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)], W.BOOL),
            (self.kernel, 'GetProcessTimes', [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4, W.BOOL),
            (self.wts, 'WTSRegisterSessionNotification', [W.HWND, W.DWORD], W.BOOL),
            (self.wts, 'WTSUnRegisterSessionNotification', [W.HWND], W.BOOL),
        ]
        for dll, name, args, result in signatures:
            fn = getattr(dll, name); fn.argtypes = args; fn.restype = result

    def identity(self, hwnd):
        if not hwnd or not self.user.IsWindow(hwnd):
            raise RuntimeError('游戏窗口已关闭')
        pid = W.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise ctypes.WinError(ctypes.get_last_error())
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            name = ctypes.create_unicode_buffer(32768); length = W.DWORD(len(name))
            times = [W.FILETIME() for _ in range(4)]
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            if os.path.basename(name.value).lower() != GAME_EXE:
                raise RuntimeError('窗口不属于伊瑟游戏进程')
            return pid.value, name.value, times[0].dwHighDateTime, times[0].dwLowDateTime
        finally:
            self.kernel.CloseHandle(handle)

    def windows(self):
        results = []
        callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        def collect(hwnd, _):
            if self.user.IsWindowVisible(hwnd):
                try:
                    identity = self.identity(hwnd)
                    results.append((hwnd, identity, self.size(hwnd)))
                except (OSError, RuntimeError):
                    pass
            return True
        self.user.EnumWindows.argtypes = [callback_type, W.LPARAM]
        self.user.EnumWindows.restype = W.BOOL
        if not self.user.EnumWindows(callback_type(collect), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return results

    def size(self, hwnd):
        rect = W.RECT()
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rect.right - rect.left, rect.bottom - rect.top

    def validate(self, target):
        hwnd, identity, size = target
        if self.identity(hwnd) != identity:
            raise RuntimeError('游戏进程或窗口已变化，请重新选择')
        current = self.size(hwnd)
        if current != size:
            raise RuntimeError(f'游戏客户区尺寸已变化（{size[0]}×{size[1]} → {current[0]}×{current[1]}），请恢复窗口后重新取点')

    def calibrate(self, target):
        """Accept fresh geometry only during explicit setup, never during a trial."""
        hwnd, identity, _ = target
        if self.identity(hwnd) != identity:
            raise RuntimeError('游戏进程或窗口已变化，请重新选择')
        if self.user.IsIconic(hwnd):
            raise RuntimeError('取点前请恢复游戏窗口')
        size = self.size(hwnd)
        if not all(0 < dimension <= 32768 for dimension in size):
            raise RuntimeError('游戏客户区尺寸无效，请恢复游戏窗口后取点')
        return hwnd, identity, size

    def point(self, target):
        self.validate(target)
        hwnd = target[0]; point = W.POINT()
        if self.user.IsIconic(hwnd):
            raise RuntimeError('取点前请恢复游戏窗口')
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        under = self.user.WindowFromPoint(point)
        if self.user.GetAncestor(under, 2) != hwnd:
            raise RuntimeError('鼠标须停在选定游戏窗口内部')
        if not self.user.ScreenToClient(hwnd, ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not (0 <= point.x < target[2][0] and 0 <= point.y < target[2][1]):
            raise RuntimeError('鼠标须停在游戏画面内部，不能停在标题栏或边框')
        return point.x, point.y

    def click(self, target, point):
        self.validate(target)
        x, y = point; width, height = target[2]
        if not (0 <= x < min(width, 32768) and 0 <= y < min(height, 32768)):
            raise ValueError('点击位置超出游戏客户区')
        packed = (y << 16) | x
        for message, flags in ((0x200, 0), (0x201, 1), (0x202, 0)):
            if not self.user.PostMessageW(target[0], message, flags, packed):
                error = ctypes.get_last_error()
                # Best effort release when the down message was already queued.
                self.user.PostMessageW(target[0], 0x202, 0, packed)
                raise ctypes.WinError(error)


@dataclass(frozen=True)
class Step:
    name: str
    point: tuple
    wait: float


class Trial:
    """Explicit polling; no catch-up bursts after sleep or a stalled event loop."""
    def __init__(self, backend, clock=time.monotonic, report=lambda message: None):
        self.backend = backend; self.clock = clock; self.report = report
        self.running = False; self.completed = 0

    def start(self, target, steps, rounds, seconds):
        if self.running:
            raise RuntimeError('试验正在运行')
        steps = tuple(steps)
        if not steps or not 1 <= rounds <= 20 or not 10 <= seconds <= 7200:
            raise ValueError('试验次数或时限无效')
        for step in steps:
            x, y = step.point; width, height = target[2]
            if not 1 <= step.wait <= 3600 or not (0 <= x < min(width, 32768) and 0 <= y < min(height, 32768)):
                raise ValueError('请先设置有效的点击位置和等待时间')
        self.backend.validate(target)
        self.target = target; self.steps = steps; self.rounds = rounds
        self.completed = 0; self.index = 0
        now = self.clock(); self.end = now + seconds; self.due = now + steps[0].wait
        self.running = True
        self.report('开始试验；循环计数只表示消息已发送，不表示副本完成')

    def stop(self, reason='已手动停止'):
        if self.running:
            self.running = False; self.report(reason)

    def tick(self):
        if not self.running:
            return
        now = self.clock()
        if now >= self.end:
            self.stop('达到总时限，已停止'); return
        if now < self.due:
            return
        if now - self.due > 10:
            self.stop('执行延迟超过10秒，已停止；不补发积压点击'); return
        step = self.steps[self.index]
        try:
            self.backend.click(self.target, step.point)
        except Exception as exc:
            self.stop(f'操作失败，已停止：{exc}'); return
        self.report(f'第{self.completed + 1}轮 · {step.name}：消息已发送，游戏响应待核实')
        self.index += 1
        if self.index == len(self.steps):
            self.completed += 1; self.index = 0
            if self.completed >= self.rounds:
                self.stop('达到试验轮数，已停止'); return
        self.due = self.clock() + self.steps[self.index].wait
