"""Compare the current setup with a hypothetical setup on the same panel."""
from dataclasses import replace
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QCheckBox,QPushButton,QPlainTextEdit
from damage_calculator import calculate
from calculator_formula import formula_text

MATRICES={'harvest':'收割','fury':'狂怒','insight':'洞悉穿刺','boiling':'沸腾打击'}

class ComparisonDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner
        self.setWindowTitle('套装与智壳 · 同面板比较');self.resize(840,580)
        root=QVBoxLayout(self)
        note=QLabel('A 使用当前配置；B 更换智壳或勾选矩阵。双方基础面板、技能和目标状态相同。仅比较效果，不重算换装副属性，也不检查配装点数。')
        note.setWordWrap(True);root.addWidget(note)
        row=QHBoxLayout();root.addLayout(row);row.addWidget(QLabel('B 智壳'))
        self.shell=QComboBox();self.shell.addItems([owner.shell.itemText(i) for i in range(owner.shell.count())]);self.shell.setCurrentText(owner.shell.currentText());row.addWidget(self.shell)
        self.tiger=QComboBox()
        for i in range(owner.tiger_target.count()):self.tiger.addItem(owner.tiger_target.itemText(i),owner.tiger_target.itemData(i))
        self.tiger.setCurrentIndex(owner.tiger_target.currentIndex());row.addWidget(self.tiger);row.addStretch()
        row=QHBoxLayout();root.addLayout(row);row.addWidget(QLabel('B 矩阵'));self.flags={}
        for key,title in MATRICES.items():
            w=QCheckBox(title);w.setChecked(getattr(owner,key).isChecked());row.addWidget(w);self.flags[key]=w
        row.addStretch();self.output=QPlainTextEdit();self.output.setReadOnly(True);root.addWidget(self.output,1)
        self.shell.currentIndexChanged.connect(self.refresh);self.tiger.currentIndexChanged.connect(self.refresh)
        for w in self.flags.values():w.toggled.connect(self.refresh)
        close=QPushButton('关闭');close.clicked.connect(self.accept);root.addWidget(close);self.refresh()
    def refresh(self,*_):
        self.tiger.setEnabled(self.shell.currentText()=='寅虎')
        try:
            a=self.owner.scenario()
            b=replace(self.owner.scenario(shell_override=self.shell.currentText(),tiger_override=self.tiger.currentData()),
                      **{k:w.isChecked() for k,w in self.flags.items()})
            ra,rb=calculate(a),calculate(b)
        except ValueError as exc:self.output.setPlainText('无法比较：'+str(exc));return
        total=lambda r:sum(v['direct']+v['shell'] for v in r['rows'])
        diff=total(rb)-total(ra);pct=f'（{diff/total(ra):+.1%}）' if total(ra)>0 else ''
        title=lambda s:s.shell+' / '+('、'.join(v for k,v in MATRICES.items() if getattr(s,k)) or '无所列矩阵')
        lines=[f'A　{title(a)}',self.owner.result_text(ra),f'B　{title(b)}',self.owner.result_text(rb),
               f'B 相对 A：结算伤害 {diff:+,.1f}{pct}；实际扣血 {rb["damage"]-ra["damage"]:+,.1f}。',
               '下方逐段列出收割、护盾、浴血、标记及击杀前的伤害。', '【A】',formula_text(a,ra),'【B】',formula_text(b,rb)]
        self.output.setPlainText('\n'.join(lines))
