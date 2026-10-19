"""Scrollable, multi-select equipment filters using the existing Qt theme."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QLabel, QPushButton, QGridLayout
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
