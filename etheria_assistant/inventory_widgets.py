"""Inventory filters and matrix distribution using the existing Qt theme."""
from collections import Counter

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QPushButton, QGridLayout, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView)
from core import matrix_name
from equipment import normalize_filters


class GearFilterDialog(QDialog):
    def __init__(self, options, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle('源器分类筛选'); self.resize(680,760); self.setMinimumSize(480,480)
        root = QVBoxLayout(self)
        title = QLabel('源器分类筛选'); title.setObjectName('title'); root.addWidget(title)
        hint = QLabel('同类选项满足任意一项；副属性需全部具备。不同类别同时生效。')
        hint.setWordWrap(True); hint.setObjectName('hint'); root.addWidget(hint)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); root.addWidget(scroll,1)
        body = QWidget(); layout = QVBoxLayout(body); scroll.setWidget(body)
        self.choices = {}; selected = normalize_filters(selected)
        titles = {'matrix':'矩阵 · 可多选','points':'矩阵点数 · 可多选','rarity':'稀有度 · 可多选',
                  'initial':'初始副属性条数 · 可多选','main':'主属性 · 可多选','subs':'副属性 · 需同时满足'}
        for key, values in options.items():
            heading = QLabel(titles[key]); heading.setObjectName('hero'); layout.addWidget(heading)
            grid = QGridLayout(); layout.addLayout(grid); self.choices[key] = {}
            for i,(value,text) in enumerate(values):
                b = QPushButton(text); b.setObjectName('filterChip'); b.setCheckable(True)
                b.setChecked(str(value) in selected[key]); b.setMinimumHeight(42)
                grid.addWidget(b,i//2,i%2); self.choices[key][str(value)] = b
        layout.addStretch()
        note = QLabel('稀有度未知时可校正。初始副属性条数只采用明确的0级观测或手工记录，不从满级条数倒推。')
        note.setWordWrap(True); note.setObjectName('hint'); root.addWidget(note)
        actions = QHBoxLayout(); root.addLayout(actions)
        clear = QPushButton('清空选择'); clear.clicked.connect(self.clear); actions.addWidget(clear)
        actions.addStretch(); cancel = QPushButton('取消'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        apply = QPushButton('应用筛选'); apply.setObjectName('primary'); apply.clicked.connect(self.accept); actions.addWidget(apply)

    def clear(self):
        for choices in self.choices.values():
            for b in choices.values(): b.setChecked(False)

    def selected(self):
        return normalize_filters({key:[v for v,b in choices.items() if b.isChecked()] for key,choices in self.choices.items()})


class MatrixPie(QWidget):
    def __init__(self):
        super().__init__()
        self.segments = []
        self.total = 0
        self.setMinimumSize(240, 240)
        self.setAccessibleName('源器矩阵分布饼图')

    def set_distribution(self, segments):
        self.segments = segments
        self.total = sum(count for _, count, _ in segments)
        self.setAccessibleDescription('；'.join(f'{name} {count} 件' for name, count, _ in segments))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 24
        circle = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#382f45'))
        painter.drawEllipse(circle)
        counted = 0
        angle = 0
        for _, count, color in self.segments:
            counted += count
            end = round(5760 * counted / self.total)
            painter.setBrush(color)
            painter.drawPie(circle, 1440 - angle, angle - end)
            angle = end
        hole = circle.adjusted(side * .28, side * .28, -side * .28, -side * .28)
        painter.setBrush(QColor('#1c1925'))
        painter.drawEllipse(hole)
        font = painter.font()
        font.setPixelSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor('#f2eef8'))
        painter.drawText(hole, Qt.AlignmentFlag.AlignCenter, f'{self.total:,}' if self.total else '无数据')
        painter.end()


class GearDistributionDialog(QDialog):
    def __init__(self, gear, mappings, minimum=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle('源器矩阵分布')
        self.resize(760, 520)
        self.gear = {item['uid']: item for item in gear}
        self.mappings = mappings
        matrices = sorted({(item.get('matrix') or {}).get('id') for item in self.gear.values()
                           if type((item.get('matrix') or {}).get('id')) is int})
        self.colors = {identifier: QColor.fromHsv((index * 137) % 360, 150, 238)
                       for index, identifier in enumerate(matrices)}

        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('最低强化等级'))
        self.level = QComboBox()
        self.level.addItem('不限等级', 0)
        for level in range(1, 16):
            self.level.addItem(f'+{level} 及以上', level)
        self.level.setCurrentIndex(max(0, self.level.findData(minimum)))
        bar.addWidget(self.level)
        bar.addStretch()
        self.total_label = QLabel()
        bar.addWidget(self.total_label)
        root.addLayout(bar)
        content = QHBoxLayout()
        self.pie = MatrixPie()
        content.addWidget(self.pie, 1)
        self.legend = QTableWidget(0, 3)
        self.legend.setHorizontalHeaderLabels(['矩阵', '件数', '占比'])
        self.legend.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.legend.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.legend.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.legend.verticalHeader().hide()
        self.legend.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.legend.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        content.addWidget(self.legend, 1)
        root.addLayout(content, 1)
        self.level.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        minimum = self.level.currentData()
        counts = Counter()
        for item in self.gear.values():
            level = item.get('level')
            if minimum and (type(level) is not int or level < minimum):
                continue
            counts[(item.get('matrix') or {}).get('id')] += 1
        ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0] is None, pair[0] or 0))
        segments = [(matrix_name(self.mappings, identifier) if identifier is not None else '未知矩阵',
                     count, self.colors.get(identifier, QColor('#9991a8'))) for identifier, count in ordered]
        self.pie.set_distribution(segments)
        total = self.pie.total
        self.total_label.setText(f'当前库存符合条件 {total:,} 件')
        self.legend.setRowCount(len(segments))
        for row, (name, count, color) in enumerate(segments):
            title = QTableWidgetItem('■  ' + name)
            title.setForeground(color)
            self.legend.setItem(row, 0, title)
            for col, value in enumerate((f'{count:,}', f'{count / total:.1%}'), 1):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.legend.setItem(row, col, cell)

