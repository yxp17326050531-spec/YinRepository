"""Native snapshot calculator; edits never flow back to the battle archive."""
from __future__ import annotations

import copy
from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFormLayout, QGroupBox, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QTabWidget, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView)
from damage_calculator import Fighter, Scenario, MODELS, import_unit, calculate
from battle_attributes import EXTRA_ATTRIBUTES

LABELS = {'attack': '攻击', 'defense': '防御', 'hp': '最大生命', 'crit': '暴击率 %',
          'crit_damage': '暴击伤害 %', 'pvp_damage_bonus': 'PVP增伤 %',
          'pvp_damage_reduction': 'PVP减伤 %', 'extra_damage_reduction': '额外减伤 %',
          'ignore_defense': '无视防御 %', 'damage_result_bonus': '结果增伤 %',
          'damage_result_reduction': '结果减伤 %'}


def plain(text=''):
    w = QLabel(text)
    w.setWordWrap(True)
    w.setTextFormat(Qt.TextFormat.PlainText)
    return w


def number(value=0, maximum=1000, missing=False):
    w = QDoubleSpinBox()
    w.setRange(-1 if missing else 0, maximum)
    w.setDecimals(2)
    w.setGroupSeparatorShown(True)
    w.setMinimumWidth(110)
    if missing:
        w.setSpecialValueText('未采集 / 请填写')
    w.setValue(-1 if value is None else value)
    w.setKeyboardTracking(False)
    return w


class DamageCalculatorDialog(QDialog):
    def __init__(self, parent, battle=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('伤害试算 · 对局快照')
        self.resize(1100, 790)
        self.setMinimumSize(760, 560)
        self.snapshot = copy.deepcopy(battle or {})
        self.units = [(team, i, u) for team, rows in self.snapshot.get('teams', {}).items()
                      for i, u in enumerate(rows)]
        self.last_result = None
        layout = QVBoxLayout(self)
        intro = plain('从本场快照导入；可改数值，不影响对局记录。按确定的暴击状态试算，不等于实测伤害。')
        layout.addWidget(intro)
        bar = QHBoxLayout()
        self.attacker_select, self.defender_select = QComboBox(), QComboBox()
        for select in (self.attacker_select, self.defender_select):
            select.addItem('手动填写', None)
            for n, (team, i, unit) in enumerate(self.units):
                select.addItem(f'{team}方 · {i+1} · {unit.get("hero_name", "角色 #"+str(unit.get("hero_id", "?")))}', n)
            select.setMinimumContentsLength(10)
            select.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        bar.addWidget(plain('攻方')); bar.addWidget(self.attacker_select, 1)
        swap = QPushButton('⇄'); swap.setToolTip('交换攻守并重新导入'); swap.clicked.connect(self.swap)
        bar.addWidget(swap); bar.addWidget(plain('守方')); bar.addWidget(self.defender_select, 1)
        reload_button = QPushButton('重新导入双方'); reload_button.clicked.connect(self.reload)
        bar.addWidget(reload_button); layout.addLayout(bar)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.fields, self.source_labels = {}, {}
        panels = QWidget(); grid = QHBoxLayout(panels)
        for role, title in (('attacker', '攻方'), ('defender', '守方')):
            group = QGroupBox(title); form = QFormLayout(group)
            self.source_labels[role] = plain(); form.addRow(self.source_labels[role])
            self.fields[role] = {}
            for key in LABELS:
                w = number(None, 1_000_000_000 if key in ('hp', 'attack', 'defense') else 10000, True)
                w.setObjectName(f'calculator_{role}_{key}')
                self.fields[role][key] = w; form.addRow(LABELS[key], w)
            grid.addWidget(group, 1)
        self.add_scroll_tab(panels, '双方属性')

        settings = QWidget(); columns = QHBoxLayout(settings)
        skill_box = QGroupBox('技能与公式'); skill = QFormLayout(skill_box)
        self.model = QComboBox()
        for key, title in MODELS.items(): self.model.addItem(title, key)
        skill.addRow('防御模型', self.model)
        self.pvp = QCheckBox('PVP：全局0.7，并启用双方PVP字段'); self.pvp.setChecked(True)
        skill.addRow(self.pvp)
        self.preset = QComboBox(); self.preset.addItems(['自定义技能', '魁洛三段大招（研究模板）'])
        self.preset.currentIndexChanged.connect(self.apply_preset); skill.addRow('技能模板', self.preset)
        self.scaling = QComboBox()
        for title, key in [('攻击', 'attack'), ('防御', 'defense'), ('最大生命', 'hp')]: self.scaling.addItem(title, key)
        skill.addRow('倍率缩放', self.scaling)
        self.hits = QSpinBox(); self.hits.setRange(1, 20); skill.addRow('段数', self.hits)
        self.ratio = number(100, 100000); skill.addRow('每段倍率 %', self.ratio)
        self.ratios = QLineEdit(); self.ratios.setPlaceholderText('可留空；例：110, 110, 150（%）')
        skill.addRow('不同段倍率', self.ratios)
        self.critical = QCheckBox('假设每段暴击'); self.critical.setChecked(True); skill.addRow(self.critical)
        self.target_multiplier = number(1, 100); skill.addRow('主目标独立乘数', self.target_multiplier)
        self.damage_multiplier = number(1, 100); skill.addRow('其他独立乘数', self.damage_multiplier)
        self.quilo_passive = QCheckBox('魁洛残心：攻差×0.03%，上限90%'); skill.addRow(self.quilo_passive)
        self.remaining_hp = number(None, 1_000_000_000, True)
        self.remaining_hp.setSpecialValueText('按守方满血'); skill.addRow('守方当前生命', self.remaining_hp)
        self.bloodbath_spent = number(0, 1_000_000_000); skill.addRow('浴血本回合已扣血', self.bloodbath_spent)
        skill.addRow(plain('不同段倍率填写后覆盖段数与每段倍率。当前生命与本回合已扣血需手填；抓包面板不是实时生命。'))
        columns.addWidget(skill_box, 1)

        effects_box = QGroupBox('增减益与条件效果'); effects = QFormLayout(effects_box)
        self.attack_up = number(); effects.addRow('其他攻击增加 %', self.attack_up)
        self.durand = QCheckBox('杜兰铎：攻击增加48%'); effects.addRow(self.durand)
        self.flower = QComboBox()
        for title, val in [('无花种', 0), ('艾莉尔：1层 +6%', 6), ('艾莉尔：2层 +12%', 12), ('已转化增益 +30%（手动确认）', 30)]: self.flower.addItem(title, val)
        effects.addRow('花种状态', self.flower)
        self.attack_down = number(0, 100); effects.addRow('攻击降低 %', self.attack_down)
        self.crit_damage_up = number(); effects.addRow('暴击伤害增加（百分点）', self.crit_damage_up)
        self.crit50 = QCheckBox('暴击伤害增加50个百分点'); effects.addRow(self.crit50)
        self.magic = QCheckBox('魔术牌：独立伤害×1.30（假设）'); effects.addRow(self.magic)
        self.defense_up = number(); effects.addRow('防御增加 %', self.defense_up)
        self.defense_down = number(0, 100); effects.addRow('防御降低 %', self.defense_down)
        self.flat_defense_down = number(0, 1_000_000); effects.addRow('固定减防', self.flat_defense_down)
        self.other_ignore = number(0, 100); effects.addRow('额外独立无视防御 %', self.other_ignore)
        self.harvest = QCheckBox('收割8：段前生命＞50%，无视40%防御')
        self.fury = QCheckBox('狂怒8：暴击结果增伤12%（同结果区）')
        self.boiling = QCheckBox('沸腾打击12：各段×1 / 1.4 / 1.8（上限）')
        self.bloodbath = QCheckBox('守方浴血12：回合扣血超20%部分减伤55%')
        for w in (self.harvest, self.fury, self.boiling, self.bloodbath): effects.addRow(w)
        self.shell = QComboBox(); self.shell.addItems(['无 / 手动', '启示录', '伯爵']); effects.addRow('攻方智壳', self.shell)
        self.enable_shell = QCheckBox('启用智壳研究模型（触发与结算待实测）'); effects.addRow(self.enable_shell)
        self.count_version = QComboBox(); self.count_version.addItems(['旧表格：固定攻击+1200', '假设：+1200及基础面板攻击的10%'])
        effects.addRow('伯爵版本', self.count_version)
        columns.addWidget(effects_box, 1)
        self.add_scroll_tab(settings, '技能与增减益')

        process = QWidget(); p = QVBoxLayout(process)
        self.process_table = QTableWidget(0, 8)
        self.process_table.setHorizontalHeaderLabels(['段', '段前生命', '有效防御', '收割', '技能伤害', '启示录伤害', '实际扣血', '剩余生命'])
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        p.addWidget(self.process_table)
        self.detail = plain(); p.addWidget(self.detail)
        self.tabs.addTab(process, '计算过程')
        self.assume_zero = QCheckBox('缺失的增减伤字段暂按0试算（不代表已确认0；不会补入原记录）')
        layout.addWidget(self.assume_zero)
        self.warning = plain(''); layout.addWidget(self.warning)
        self.result_label = plain('选择双方并核实技能，然后点击计算。'); self.result_label.setObjectName('title')
        layout.addWidget(self.result_label)
        footer = QHBoxLayout()
        self.calculate_button = QPushButton('计算并显示分段'); self.calculate_button.setObjectName('primary')
        self.calculate_button.clicked.connect(self.run); footer.addWidget(self.calculate_button)
        self.compare_button = QPushButton('对比收割 / 狂怒'); self.compare_button.clicked.connect(self.compare)
        footer.addWidget(self.compare_button); footer.addStretch()
        close = QPushButton('关闭'); close.clicked.connect(self.close); footer.addWidget(close); layout.addLayout(footer)
        self.attacker_select.currentIndexChanged.connect(lambda: self.load_role('attacker'))
        self.defender_select.currentIndexChanged.connect(lambda: self.load_role('defender'))
        # Never leave a result from old inputs visible as if it were current.
        for w in self.findChildren(QDoubleSpinBox): w.valueChanged.connect(self.invalidate)
        self.hits.valueChanged.connect(self.invalidate); self.ratios.textChanged.connect(self.invalidate)
        for w in self.findChildren(QCheckBox): w.toggled.connect(self.invalidate)
        for w in (self.model, self.scaling, self.preset, self.flower, self.shell, self.count_version):
            w.currentIndexChanged.connect(self.invalidate)
        if self.units:
            self.attacker_select.setCurrentIndex(1)
            attack_team = self.units[0][0]
            opposite = next((n + 1 for n, (t, _, _) in enumerate(self.units) if t != attack_team), 0)
            self.defender_select.setCurrentIndex(opposite)
        self.reload()

    def add_scroll_tab(self, widget, title):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget)
        self.tabs.addTab(scroll, title)

    def invalidate(self, *_):
        self.last_result = None
        self.result_label.setText('参数已变化，请重新计算。')
        self.process_table.setRowCount(0); self.detail.setText('')

    def apply_preset(self, index):
        self.scaling.setCurrentIndex(0); self.ratios.clear()
        self.hits.setValue(3 if index else 1); self.ratio.setValue(110 if index else 100)
        self.target_multiplier.setValue(1.75 if index else 1)
        self.quilo_passive.setChecked(bool(index))

    def load_role(self, role):
        select = self.attacker_select if role == 'attacker' else self.defender_select
        idx = select.currentData()
        data = import_unit(self.units[idx][2]) if idx is not None else None
        for key, w in self.fields[role].items():
            w.setValue(data['values'].get(key) if data and data['values'].get(key) is not None else -1)
        if data:
            extra_labels = dict(EXTRA_ATTRIBUTES.values())
            unmodeled = '、'.join(f'{extra_labels.get(k, k)}={v:g}%' for k, v in data['unapplied_extras'].items())
            source = '矩阵：' + ('、'.join(data['matrices']) or '未确认 / 无手动矩阵')
            source += '\n智壳：' + (' / '.join(data['shell_names']) or '未确认')
            if unmodeled: source += '\n尚未套用：' + unmodeled
            source += '\n开场快照；暴击相关字段仍属暂定解码。'
            self.source_labels[role].setText(source)
        else:
            self.source_labels[role].setText('未导入角色，请手动填写。')
        active = data['active_effects'] if data else set()
        if role == 'attacker':
            for name, w in (('收割', self.harvest), ('狂怒', self.fury), ('沸腾打击', self.boiling)):
                w.setChecked(name in active)
            self.shell.setCurrentText(data['shell'] if data else '无 / 手动')
            self.enable_shell.setChecked(False)
        else:
            self.bloodbath.setChecked('浴血之躯' in active)
            self.remaining_hp.setValue(-1); self.bloodbath_spent.setValue(0)
        self.invalidate()

    def reload(self):
        self.load_role('attacker'); self.load_role('defender')
        self.warning.setText('已导入快照。候选矩阵不会自动启用；智壳只导入名称，需勾选研究模型。')

    def swap(self):
        a, d = self.attacker_select.currentIndex(), self.defender_select.currentIndex()
        self.attacker_select.blockSignals(True); self.defender_select.blockSignals(True)
        self.attacker_select.setCurrentIndex(d); self.defender_select.setCurrentIndex(a)
        self.attacker_select.blockSignals(False); self.defender_select.blockSignals(False)
        self.reload()

    def scenario(self):
        required = {'attacker': {self.scaling.currentData()}, 'defender': {'hp', 'defense'}}
        shell = self.shell.currentText() if self.enable_shell.isChecked() else '无 / 手动'
        if self.quilo_passive.isChecked(): required['defender'].add('attack')
        if self.quilo_passive.isChecked() or shell != '无 / 手动': required['attacker'].add('attack')
        if self.critical.isChecked(): required['attacker'].add('crit_damage')
        extra_required = {'attacker': {'ignore_defense', 'damage_result_bonus'},
                          'defender': {'extra_damage_reduction', 'damage_result_reduction'}}
        if self.pvp.isChecked():
            extra_required['attacker'].add('pvp_damage_bonus')
            extra_required['defender'].add('pvp_damage_reduction')
        missing, zero, fighters = [], [], {}
        for role, fields in self.fields.items():
            values = {}
            for key, w in fields.items():
                val = w.value()
                if val < 0:
                    if key in required[role]: missing.append(('攻方' if role == 'attacker' else '守方') + LABELS[key])
                    elif key in extra_required[role]: zero.append(('攻方' if role == 'attacker' else '守方') + LABELS[key])
                if key != 'crit': values[key] = max(0, val) if key != 'hp' or val >= 0 else 1
            fighters[role] = Fighter(**values)
        if missing: raise ValueError('请填写必要面板：' + '、'.join(missing))
        if zero and not self.assume_zero.isChecked():
            raise ValueError('增减伤字段缺失，请填写或勾选暂按0：' + '、'.join(zero))
        ratio_text = self.ratios.text().strip().replace('，', ',')
        try:
            ratios = tuple(float(v.strip()) / 100 for v in ratio_text.split(',')) if ratio_text else (self.ratio.value() / 100,) * self.hits.value()
        except ValueError: raise ValueError('不同段倍率请使用逗号分隔的数字，例如110,110,150')
        a, d = self.attacker_select.currentData(), self.defender_select.currentData()
        if a is not None and d is not None and self.units[a][0] == self.units[d][0]:
            raise ValueError('请选择来自不同队伍的攻方与守方；也可改为手动填写')
        self.warning.setText(('缺失暂按0：' + '、'.join(zero) + '。' if zero else '') +
            '模型假设：不含护盾、不死、队友分摊及未建模被动；未套用字段见属性页。')
        return Scenario(attacker=fighters['attacker'], defender=fighters['defender'],
            model=self.model.currentData(), scaling=self.scaling.currentData(), ratios=ratios,
            critical=self.critical.isChecked(), pvp=self.pvp.isChecked(),
            attack_up=self.attack_up.value() + (48 if self.durand.isChecked() else 0) + self.flower.currentData(),
            attack_down=self.attack_down.value(), crit_damage_up=self.crit_damage_up.value() + (50 if self.crit50.isChecked() else 0),
            defense_up=self.defense_up.value(), defense_down=self.defense_down.value(), flat_defense_down=self.flat_defense_down.value(),
            other_ignore=self.other_ignore.value(), damage_multiplier=self.damage_multiplier.value() * (1.3 if self.magic.isChecked() else 1),
            target_multiplier=self.target_multiplier.value(), harvest=self.harvest.isChecked(), fury=self.fury.isChecked(),
            boiling=self.boiling.isChecked(), bloodbath=self.bloodbath.isChecked(), bloodbath_spent=self.bloodbath_spent.value(),
            remaining_hp=self.remaining_hp.value() if self.remaining_hp.value() >= 0 else None, shell=shell,
            count_attack_percent=10 if self.count_version.currentIndex() else 0, quilo_passive=self.quilo_passive.isChecked())

    @staticmethod
    def result_text(r):
        state = f'模型预测第{r["kill_hit"]}段击杀' if r['killed'] else f'模型预测未击杀，剩余 {r["remaining"]:,.1f}'
        return f'{state} · 实际扣血 {r["damage"]:,.1f}'

    def run(self):
        try:
            s = self.scenario(); r = calculate(s)
        except ValueError as e:
            self.invalidate(); self.result_label.setText(str(e)); return
        self.last_result = r
        self.result_label.setText(self.result_text(r))
        self.process_table.setRowCount(len(r['rows']))
        for row, hit in enumerate(r['rows']):
            values = [str(hit['hit']), f'{hit["before"]:,.1f}', f'{hit["effective_defense"]:,.2f}',
                      '触发' if hit['harvest'] else '—', f'{hit["direct"]:,.1f}', f'{hit["shell"]:,.1f}',
                      f'{hit["actual"]:,.1f}', f'{hit["remaining"]:,.1f}']
            for col, text in enumerate(values): self.process_table.setItem(row, col, QTableWidgetItem(text))
        other = calculate(replace(s, model='kzone' if s.model == 'template' else 'template'))
        self.detail.setText(f'{MODELS[s.model]} · 战斗攻击 {r["combat_attack"]:,.2f} · 残心乘数 {r["passive_multiplier"]:.3f}\n'
            f'另一公式仅供对照：{MODELS[other["model"]]} → {self.result_text(other)}\n'
            '技能/智壳伤害含溢出；实际扣血封顶到当前生命。死亡即停止后续段与智壳触发。两套公式均待游戏实测。')
        self.tabs.setCurrentIndex(2)

    def compare(self):
        try:
            s = self.scenario()
            h = calculate(replace(s, harvest=True, fury=False))
            f = calculate(replace(s, harvest=False, fury=True))
        except ValueError as e:
            self.invalidate(); self.result_label.setText(str(e)); return
        self.last_result = None; self.process_table.setRowCount(0)
        self.result_label.setText('收割：' + self.result_text(h) + '\n狂怒：' + self.result_text(f))
        self.detail.setText('只替换8点效果，其他属性保持相同；未模拟换装后副属性变化。\n'
                            '双方都击杀时实际扣血相同，应比较击杀段数。')
        self.tabs.setCurrentIndex(2)
