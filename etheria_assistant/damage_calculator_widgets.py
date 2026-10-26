"""Native snapshot calculator; edits never flow back to the battle archive."""
from __future__ import annotations

import copy
from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QFormLayout, QGroupBox, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QTabWidget, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout, QStackedWidget)
from damage_calculator import Fighter, Scenario, MODELS, import_unit, calculate
from battle_attributes import EXTRA_ATTRIBUTES
from calculator_statuses import STATUSES, apply_statuses
from character_presets import CHARACTERS, apply_character

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
        self.affinity=QComboBox()
        for name,key in [('无克制 / 未确认','neutral'),('攻方克制守方：伤害×1.15','advantage'),('攻方被克制：伤害×0.85','disadvantage')]:self.affinity.addItem(name,key)
        skill.addRow('相性关系',self.affinity)
        self.affinity.currentIndexChanged.connect(self.invalidate)
        self.pvp = QCheckBox('PVP：全局0.7，并启用双方PVP字段'); self.pvp.setChecked(True)
        skill.addRow(self.pvp)
        self.preset = QComboBox(); self.preset.addItems(['自定义技能']+list(CHARACTERS))
        self.preset.currentIndexChanged.connect(self.apply_preset); skill.addRow('角色预设', self.preset)
        self.character_skill=QComboBox();self.character_skill.currentIndexChanged.connect(self.apply_character_skill);skill.addRow('角色技能',self.character_skill)
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
        self.fury = QCheckBox('狂怒8：暴击伤害独立×1.12（与面板结果增伤乘算）')
        self.boiling = QCheckBox('沸腾打击12：各段×1 / 1.4 / 1.8（上限）')
        self.bloodbath = QCheckBox('守方浴血12：回合扣血超20%部分减伤55%')
        for w in (self.harvest, self.fury, self.boiling, self.bloodbath): effects.addRow(w)
        self.shell = QComboBox(); self.shell.addItems(['无 / 手动', '启示录', '伯爵', '噬身之蛇', '宝剑七', '白獠武者（博尔涅联动）', '寅虎（先手待建模）']); effects.addRow('攻方智壳', self.shell)
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
        statuses = QWidget(); states_layout = QVBoxLayout(statuses)
        states_layout.addWidget(plain('选择当前已生效状态，不自动推断技能或层数。每侧独立；不要与原有花种、手填增减益重复填写。不同命名增减伤暂按独立乘区假设。待补充项可选，但会阻止输出击杀结论。'))
        states_grid = QGridLayout(); states_layout.addLayout(states_grid)
        states_grid.addWidget(plain('效果与说明'), 0, 0)
        states_grid.addWidget(plain('攻方当前状态'), 0, 1)
        states_grid.addWidget(plain('守方当前状态'), 0, 2)
        self.status_states = {'attacker': {}, 'defender': {}}
        for row, (key, title, desc, maximum, supported) in enumerate(STATUSES, 1):
            name = plain(title + (' · 待补充/建模' if not supported else ''))
            name.setToolTip(desc); states_grid.addWidget(name, row, 0)
            for col, role in enumerate(('attacker', 'defender'), 1):
                choice = QComboBox(); choice.addItem('无', 0)
                for n in range(1, maximum+1):
                    text = (f'生效 · 额外基础增益{n-1}种' if key == 'sun' else '明花彩' if key == 'flower' and n == 3 else f'{n}档（每档500入场防）' if key == 'execution' else f'{n}层/次' if maximum > 1 else '生效')
                    choice.addItem(text, n)
                choice.setToolTip(desc); choice.currentIndexChanged.connect(self.invalidate)
                self.status_states[role][key] = choice; states_grid.addWidget(choice, row, col)
        states_layout.addWidget(plain('寒玉层数仅用于确认当前技能是否受到保护，不按每一段扣层；本次试算不模拟下一个技能。心火减伤按层数同区累计。霜花的吸收部分未填容量时不能预测带盾目标击杀。'))
        self.add_scroll_tab(statuses, '角色状态（26项）')
        conditions = QWidget(); cond = QFormLayout(conditions)
        self.aoe = QCheckBox('本次为群体技能'); cond.addRow(self.aoe)
        self.secondary = QCheckBox('守方为次目标（未被选为主目标）'); cond.addRow(self.secondary)
        self.serpent = QSpinBox(); self.serpent.setRange(0,7);cond.addRow('噬身之蛇·已生效层数',self.serpent)
        self.white_stacks = QSpinBox(); self.white_stacks.setRange(0,8);cond.addRow('白獠武者·已有暴伤层数',self.white_stacks)
        self.controlled = QCheckBox('宝剑七增伤已生效，目标有持续控制（睡眠除外）');cond.addRow(self.controlled)
        self.spring = QCheckBox('守方涌泉12：承伤降低25%');cond.addRow(self.spring)
        self.unyielding = QCheckBox('守方不屈之誓12：减伤20%，段前血量低于55%翻倍');cond.addRow(self.unyielding)
        self.insight = QCheckBox('攻方洞悉穿刺12：本回合前三次伤害+25%/15%/5%');cond.addRow(self.insight)
        self.prior_events = QSpinBox();self.prior_events.setRange(0,3);cond.addRow('本回合此前伤害次数（3代表已耗尽）',self.prior_events)
        self.opportunist = QCheckBox('攻方乘势追击12：目标每种减益/控制+6%');cond.addRow(self.opportunist)
        self.debuff_count = QSpinBox();self.debuff_count.setRange(0,6);cond.addRow('目标不同减益/控制种类数',self.debuff_count)
        self.desecrate = QCheckBox('攻方亵渎8：有护盾时额外伤害+40%');cond.addRow(self.desecrate)
        self.shield_remaining = number(0,1_000_000_000);cond.addRow('守方普通护盾剩余吸收量',self.shield_remaining)
        cond.addRow(plain('矩阵基础攻/生命/暴伤已在导入面板中，不重复叠加。普通盾按伤害后吸收；与浴血同时使用暂阻止计算。洞悉按本次目标的伤害事件计数，群体多目标消耗顺序待验证。白獠暴伤为此次技能前已有层数，不推断联动。白獠仅支持博尔涅联动，两段各附加60%最大生命伤害；寅虎先手尚未建模。'))
        self.butcher_tier=QComboBox();self.butcher_tier.addItem('不启用',0)
        for val in (6.4,8.8,11.2,13.6,16):self.butcher_tier.addItem(f'{val:g}%',val)
        cond.addRow('屠夫·生命高于90%增伤',self.butcher_tier)
        self.attacker_hp_percent=number(None,100,True);cond.addRow('攻方当前生命 %',self.attacker_hp_percent)
        self.butcher_not_in_panel=QCheckBox('确认此条件加成未包含在导入面板中，按独立乘区试算');cond.addRow(self.butcher_not_in_panel)
        self.butcher_tier.currentIndexChanged.connect(self.invalidate)
        self.add_scroll_tab(conditions, '智壳与矩阵条件')
        character_page=QWidget();cp=QFormLayout(character_page)
        self.character_note=plain('角色参数只作用于当前选择的角色技能，不会写入其他角色预设。');cp.addRow(self.character_note)
        self.character_panels=QStackedWidget();cp.addRow(self.character_panels)
        for name in ['自定义技能']+list(CHARACTERS):
            panel=QWidget();form=QFormLayout(panel);self.character_panels.addWidget(panel)
            if name=='博尔涅':
                self.borne_alive=QSpinBox();self.borne_alive.setRange(0,12);self.borne_alive.setSpecialValueText('请填写');form.addRow('当前存活敌人数',self.borne_alive)
                self.borne_hp_mode=QComboBox();self.borne_hp_mode.addItems(['入场生命是否已含被动：未确认','导入生命已包含入场被动','导入生命未包含，补加8倍入场攻击']);self.borne_hp_mode.setCurrentIndex(2);form.addRow(self.borne_hp_mode)
                self.borne_entry_attack=number(0,1_000_000_000);form.addRow('入场攻击（非战斗buff后）',self.borne_entry_attack)
                self.borne_hp_damage=QComboBox();self.borne_hp_damage.addItems(['60%生命附伤口径：未确认','研究假设：每段附加','研究假设：仅第一段附加']);form.addRow(self.borne_hp_damage)
                self.borne_passive_checked=QCheckBox('天狼吠月：已手动排除目标被动，保留装备矩阵');form.addRow(self.borne_passive_checked)
            if name=='弥瑟亚':
                self.passive_checked=QCheckBox('降神：已手动排除目标被动，装备矩阵与状态来源已核实');form.addRow(self.passive_checked)
            if name=='千羽':
                self.qianyu_attack_speed=number(None,100000,True);self.qianyu_defense_speed=number(None,100000,True)
                form.addRow('攻方原面板速度',self.qianyu_attack_speed);form.addRow('守方原面板速度',self.qianyu_defense_speed)
                form.addRow(plain('释放明光裁定先加30%速度，不与同名速度上升重复叠加；状态页速度/花种/数据流/逆羽会参与速度差。已有状态若已包含在手填速度中，请勿再选一次。'))
        self.add_scroll_tab(character_page,'角色专属参数')
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
        self.hits.valueChanged.connect(self.invalidate);
        for w in (self.serpent,self.white_stacks,self.prior_events,self.debuff_count,self.borne_alive):w.valueChanged.connect(self.invalidate)
        self.ratios.textChanged.connect(self.invalidate)
        for w in self.findChildren(QCheckBox): w.toggled.connect(self.invalidate)
        for w in (self.model, self.scaling, self.preset, self.flower, self.shell, self.count_version,self.borne_hp_mode,self.borne_hp_damage):
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

    def apply_preset(self,index):
        self.character_skill.blockSignals(True);self.character_skill.clear()
        if index:
            for key,row in CHARACTERS[self.preset.currentText()]['skills'].items():self.character_skill.addItem(row['name'],key)
        self.character_skill.blockSignals(False)
        self.character_panels.setCurrentIndex(index)
        self.character_note.setText(CHARACTERS[self.preset.currentText()]['note'] if index else '自定义技能不应用角色被动。')
        self.apply_character_skill()

    def apply_character_skill(self,*_):
        key=self.character_skill.currentData();name=self.preset.currentText()
        row=CHARACTERS[name]['skills'][key] if key else {'ratios':(1.0,),'scaling':'attack','aoe':False}
        self.scaling.setCurrentIndex(self.scaling.findData(row['scaling']));self.ratios.clear()
        self.hits.setValue(len(row['ratios']));self.ratio.setValue(row['ratios'][0]*100)
        self.critical.setChecked(name!='博尔涅');self.critical.setEnabled(name!='博尔涅');self.quilo_passive.setChecked(name=='魁洛')
        self.target_multiplier.setValue(1.75 if name=='魁洛' else 1)
        self.aoe.setChecked(row['aoe']);self.secondary.setChecked(False)
        self.invalidate()

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
        speed=(self.units[idx][2].get('stats') or {}).get('speed') if idx is not None else None
        (self.qianyu_attack_speed if role=='attacker' else self.qianyu_defense_speed).setValue(speed if speed is not None else -1)
        if role == 'attacker':
            self.attacker_hp_percent.setValue(-1);self.butcher_tier.setCurrentIndex(0);self.butcher_not_in_panel.setChecked(False)
            self.borne_entry_attack.setValue(data['values'].get('attack') or 0 if data else 0)
            for name, w in (('收割', self.harvest), ('狂怒', self.fury), ('沸腾打击', self.boiling)):
                w.setChecked(name in active)
            self.shell.setCurrentText(({'白獠武者':'白獠武者（博尔涅联动）','寅虎':'寅虎（先手待建模）'}.get(data['shell'],data['shell'])) if data else '无 / 手动')
            for name,w in (('洞悉穿刺',self.insight),('乘势追击',self.opportunist),('亵渎',self.desecrate)):w.setChecked(name in active)
            self.serpent.setValue(0);self.white_stacks.setValue(0);self.prior_events.setValue(0);self.debuff_count.setValue(0)
            self.enable_shell.setChecked(False)
        else:
            self.bloodbath.setChecked('浴血之躯' in active)
            self.spring.setChecked('涌泉' in active);self.unyielding.setChecked('不屈之誓' in active)
            self.shield_remaining.setValue(0)
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
        if shell=='白獠武者（博尔涅联动）':
            if self.character_skill.currentData()!='borne_s3':raise ValueError('白獠追击目前仅支持博尔涅预设，其他角色追击尚未建模')
            if self.secondary.isChecked():raise ValueError('白獠只追击主目标，次目标请关闭智壳单独试算')
            shell='白獠武者'
        if shell == '寅虎（先手待建模）':
            raise ValueError('该智壳的独立攻击及联动尚未建模；白獠已有暴伤可在条件页单独输入')
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
        if self.butcher_tier.currentData() and not self.butcher_not_in_panel.isChecked():
            raise ValueError('屠夫：请确认未计入面板，避免重复叠加；已计入时保持不启用')
        scenario = Scenario(affinity=self.affinity.currentData(),butcher_bonus=self.butcher_tier.currentData(),
            attacker_hp_percent=self.attacker_hp_percent.value() if self.attacker_hp_percent.value()>=0 else None,spring=self.spring.isChecked(),unyielding=self.unyielding.isChecked(),
            insight=self.insight.isChecked(),prior_damage_events=self.prior_events.value(),
            opportunist=self.debuff_count.value() if self.opportunist.isChecked() else 0,
            shield_bonus=self.desecrate.isChecked(),shield_hp=self.shield_remaining.value(),
            seven_control=shell=='宝剑七' and self.controlled.isChecked(),attacker=fighters['attacker'], defender=fighters['defender'],
            model=self.model.currentData(), scaling=self.scaling.currentData(), ratios=ratios,
            critical=self.critical.isChecked(), pvp=self.pvp.isChecked(),
            attack_up=self.attack_up.value() + (48 if self.durand.isChecked() else 0) + self.flower.currentData(),
            attack_down=self.attack_down.value(), crit_damage_up=self.crit_damage_up.value() + self.white_stacks.value()*10 + (50 if self.crit50.isChecked() else 0),
            defense_up=self.defense_up.value(), defense_down=self.defense_down.value(), flat_defense_down=self.flat_defense_down.value(),
            other_ignore=self.other_ignore.value(), damage_multiplier=self.damage_multiplier.value() * (1+.1*self.serpent.value() if shell=='噬身之蛇' else 1) * (1.3 if self.magic.isChecked() else 1),
            target_multiplier=1 if self.secondary.isChecked() else self.target_multiplier.value(), harvest=self.harvest.isChecked(), fury=self.fury.isChecked(),
            boiling=self.boiling.isChecked(), bloodbath=self.bloodbath.isChecked(), bloodbath_spent=self.bloodbath_spent.value(),
            remaining_hp=self.remaining_hp.value() if self.remaining_hp.value() >= 0 else None, shell=shell,
            count_attack_percent=10 if self.count_version.currentIndex() else 0, quilo_passive=self.quilo_passive.isChecked())
        states = {role: {key: w.currentData() for key, w in fields.items() if w.currentData()}
                  for role, fields in self.status_states.items()}
        if states['attacker'].get('flower') and self.flower.currentData():
            raise ValueError('花种重复：请清除旧技能页的花种或状态页花种之一')
        if states['defender'].get('frost') and self.shield_remaining.value() <= 0:
            raise ValueError('守方霜花有吸收伤害效果，缺剩余容量，暂不能预测击杀')
        if states['defender'].get('void'):
            if not self.aoe.isChecked() or not self.secondary.isChecked():
                raise ValueError('虚无目标不能选为主目标：请确认群体技能且守方为次目标')
            from dataclasses import replace
            scenario=replace(scenario,damage_multiplier=scenario.damage_multiplier*.3)
        if states['defender'].get('shield'):
            if self.shield_remaining.value() <= 0:raise ValueError('请在条件页填写普通护盾剩余吸收量')
            states['defender'].pop('shield')
        key=self.character_skill.currentData()
        scenario=apply_character(scenario,key,alive=self.borne_alive.value(),hp_mode=self.borne_hp_mode.currentIndex(),
            entry_attack=self.borne_entry_attack.value(),hp_damage_mode=self.borne_hp_damage.currentIndex(),
            attacker_speed=self.qianyu_attack_speed.value() if self.qianyu_attack_speed.value()>=0 else None,
            defender_speed=self.qianyu_defense_speed.value() if self.qianyu_defense_speed.value()>=0 else None,
            speed_up=bool(states['attacker'].get('speed_up')),defender_speed_up=bool(states['defender'].get('speed_up')),
            attacker_speed_down=bool(states['attacker'].get('speed_down')),defender_speed_down=bool(states['defender'].get('speed_down')),
            legacy_flower=self.flower.currentData(),passive_checked=(self.borne_passive_checked.isChecked() if key=='borne_s3' else self.passive_checked.isChecked()),defense_states=states['defender'],attacker_states=states['attacker'])
        if self.critical.isChecked() and key!='borne_s3':
            crit=self.fields['attacker']['crit'].value()
            shift={'neutral':0,'advantage':15,'disadvantage':-30}[self.affinity.currentData()]
            if crit>=0 and crit+shift<=0:raise ValueError('相性修正后暴击率为0，请关闭全暴击假设')
        return apply_statuses(scenario, states['attacker'], states['defender'])

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
            values = [f'{hit["phase"]}{hit["phase_hit"]}', f'{hit["before"]:,.1f}', f'{hit["effective_defense"]:,.2f}',
                      '触发' if hit['harvest'] else '—', f'{hit["direct"]:,.1f}', f'{hit["shell"]:,.1f}',
                      f'{hit["actual"]:,.1f}', f'{hit["remaining"]:,.1f}']
            for col, text in enumerate(values): self.process_table.setItem(row, col, QTableWidgetItem(text))
        other = calculate(replace(s, model='kzone' if s.model == 'template' else 'template'))
        observed_crit=self.fields['attacker']['crit'].value()
        shift={'neutral':0,'advantage':15,'disadvantage':-30}[s.affinity]
        adjusted=max(0,min(100,observed_crit+shift)) if observed_crit>=0 else None
        affinity_note=f'相性后暴击率 {adjusted:g}%' if adjusted is not None else '相性后暴击率未采集'
        self.detail.setText(affinity_note+'；仍按选定的暴击/非暴击假设计算，未算概率。逆克制效果命中降低50%，本次不模拟效果命中。\n'+f'{MODELS[s.model]} · 战斗攻击 {r["combat_attack"]:,.2f} · 残心乘数 {r["passive_multiplier"]:.3f}\n'
            f'另一公式仅供对照：{MODELS[other["model"]]} → {self.result_text(other)}\n'
            f'剩余普通护盾 {r["rows"][-1]["shield_remaining"]:,.1f} · 技能/智壳伤害含溢出；实际扣血封顶到当前生命。死亡即停止后续段与智壳触发。两套公式均待游戏实测。')
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
