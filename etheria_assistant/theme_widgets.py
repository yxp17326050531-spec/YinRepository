"""Native window framing, sidebar icons and the overview header ornament."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QFrame

from artwork import ROOT


def apply_window_frame(window, theme):
    if QGuiApplication.platformName() != 'windows':
        return

    set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    set_attribute.restype = wintypes.LONG
    hwnd = int(window.winId())

    # Older Windows versions leave unsupported attributes at their system defaults.
    dark_mode = wintypes.BOOL(True)
    set_attribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
    colors = ('#5f503a', '#161410', '#efe7d8') if theme == 'gold' else ('#382e44', '#171420', '#dce5f0')
    # DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR use Win32 COLORREF.
    for attribute, value in zip((34, 35, 36), colors):
        color = QColor(value)
        colorref = wintypes.COLORREF(color.red() | (color.green() << 8) | (color.blue() << 16))
        set_attribute(hwnd, attribute, ctypes.byref(colorref), ctypes.sizeof(colorref))


def tinted_pixmap(name, color):
    pixmap = QPixmap(str(ROOT / 'ui' / f'{name}.png'))
    if not pixmap.isNull():
        with QPainter(pixmap) as painter:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(color))
    return pixmap


def navigation_icon(name, theme):
    colors = ('#b8ac99', '#d7b77b') if theme == 'gold' else ('#a79eb8', '#81dcfa')
    icon = QIcon()
    for color, state in zip(colors, (QIcon.State.Off, QIcon.State.On)):
        pixmap = tinted_pixmap(name, color)
        if not pixmap.isNull():
            icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return icon


class OverviewHeader(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('overviewHeader')
        self.setProperty('decorated', False)
        corner = tinted_pixmap('corner', '#b2996d')
        self.corners = [
            corner.transformed(QTransform.fromScale(x, y)).scaled(
                14, 14, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            for x, y in ((1, 1), (-1, 1), (1, -1), (-1, -1))
        ]

    def set_decorated(self, enabled):
        if self.property('decorated') == enabled:
            return
        self.setProperty('decorated', enabled)
        margins = (17, 0, 17, 0) if enabled else (0, 0, 0, 0)
        self.layout().setContentsMargins(*margins)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.property('decorated'):
            with QPainter(self) as painter:
                for index, corner in enumerate(self.corners):
                    x = self.width() - corner.width() - 3 if index % 2 else 3
                    y = self.height() - corner.height() - 3 if index >= 2 else 3
                    painter.drawPixmap(x, y, corner)
