"""Responsive Qt battle rows, with identity and two distinct attribute groups."""
from html import escape
from math import isfinite
from time import monotonic
from PySide6.QtCore import QPointF,Qt,QTimer
from PySide6.QtGui import QColor,QPainter,QPixmap,QPolygonF
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QMenu,QSizePolicy,QBoxLayout,QLayout
from artwork import image_label,matrix_color,suspected_hero_name
from capture import shell_text,matrix_text,imprint_text
from battle_attributes import component_hints, decode_extra_attributes

ATTRIBUTE_COLOR_RANGES = {
    'hp': (30000, 85000), 'attack': (3000, 5500), 'defense': (1500, 5000),
    'speed': (300, 400), 'crit': (80, 100), 'crit_damage': (200, 400),
    'effect_hit': (100, 300), 'effect_resist': (100, 300),
}
ATTRIBUTE_COLORS = ((242, 244, 252), (255, 225, 103), (255, 166, 83), (255, 95, 108))
BASE_ATTRIBUTES = (
    ('hp', '生命'), ('attack', '攻击'), ('defense', '防御'), ('speed', '速度'),
    ('crit', '暴击率'), ('crit_damage', '暴击伤害'),
    ('effect_hit', '效果命中'), ('effect_resist', '效果抵抗'),
)
BASE_PERCENT_KEYS = frozenset(key for key, _ in BASE_ATTRIBUTES[4:])
COMMON_DAMAGE_ATTRIBUTES = (
    ('pvp_damage_bonus', 'PVP增伤'), ('damage_result_bonus', '结果增伤'),
    ('ignore_defense', '无视防御'), ('pvp_damage_reduction', 'PVP减伤'),
    ('damage_result_reduction', '结果减伤'), ('extra_damage_reduction', '额外减伤'),
)
DAMAGE_ATTRIBUTES = COMMON_DAMAGE_ATTRIBUTES + (
    ('basic_damage_bonus', '普攻增伤'),
    ('basic_damage_reduction', '普攻减伤'),
    ('ultimate_damage_bonus', '终极增伤'),
    ('ultimate_damage_reduction', '终极减伤'),
    ('crit_damage_bonus', '暴击增伤'),
    ('crit_damage_reduction', '被暴击减伤'),
    ('boss_damage_bonus', '首领增伤'),
    ('potential_damage_modifier', '命座增减伤'),
)
SUPPORT_ATTRIBUTES = (
    ('healing_bonus', '施加治疗'),
    ('healing_received_bonus', '受到治疗'),
    ('shield_bonus', '施加护盾'),
    ('shield_received_bonus', '受到护盾'),
)
BATTLE_ATTRIBUTE_GROUPS = (
    ('基础属性', BASE_ATTRIBUTES), ('伤害', DAMAGE_ATTRIBUTES),
    ('治疗与护盾', SUPPORT_ATTRIBUTES),
)
ALL_BATTLE_ATTRIBUTE_KEYS = tuple(key for _, group in BATTLE_ATTRIBUTE_GROUPS for key, _ in group)
DEFAULT_BATTLE_ATTRIBUTE_KEYS = tuple(key for key, _ in BASE_ATTRIBUTES + COMMON_DAMAGE_ATTRIBUTES)


def normalize_battle_attribute_keys(saved):
    if not isinstance(saved, list):
        return DEFAULT_BATTLE_ATTRIBUTE_KEYS
    return tuple(key for key in ALL_BATTLE_ATTRIBUTE_KEYS if key in saved)


def full_potential_badge(avatar):
    size = 16
    badge = QLabel(avatar)
    badge.setObjectName('fullPotentialBadge')
    badge.setAccessibleName('满命')
    badge.setToolTip('满命 · 开场命座增减伤 10%（#38）。减伤贡献已计入额外减伤。')
    badge.setGeometry(avatar.width() - size, avatar.height() - size, size, size)
    icon = QPixmap(size * 4, size * 4)
    icon.setDevicePixelRatio(4)
    icon.fill(Qt.GlobalColor.transparent)
    with QPainter(icon) as painter:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#201825'))
        painter.drawEllipse(QPointF(8, 8), 7.6, 7.6)
        painter.setBrush(QColor('#ffd477'))
        points = ((3.2, 5.7), (5.8, 7.5), (8, 4.2), (10.2, 7.5),
                  (12.8, 5.7), (11.7, 10.8), (4.3, 10.8))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        painter.drawRoundedRect(4.4, 11.4, 7.2, 1, .45, .45)
    badge.setPixmap(icon)


def attribute_color(key, value):
    if key not in ATTRIBUTE_COLOR_RANGES or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    low, high = ATTRIBUTE_COLOR_RANGES[key]
    position = max(0.0, min(1.0, (value - low) / (high - low))) * (len(ATTRIBUTE_COLORS) - 1)
    index = min(int(position), len(ATTRIBUTE_COLORS) - 2)
    fraction = position - index
    return QColor(*(round(start + (end - start) * fraction)
                    for start, end in zip(ATTRIBUTE_COLORS[index], ATTRIBUTE_COLORS[index + 1])))


class RainbowSpeed(QLabel):
    """Cycle the text color while the exceptionally fast value is on screen."""
    def __init__(self, shown):
        super().__init__(shown)
        self.setObjectName('speed')
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_color)
        self.update_color()

    def update_color(self):
        color = QColor.fromHsvF((monotonic() / 3.0) % 1.0, .58, 1.0)
        self.setStyleSheet(f'color: {color.name()};')

    def showEvent(self, event):
        super().showEvent(event)
        self.update_color()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)


def text(value,name=None):
    w=QLabel(value);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText)
    if name:w.setObjectName(name)
    return w


class UnitCard(QFrame):
    """Show opening stats and fit the card to its team's share of the viewport."""
    def __init__(self,unit,team,action,edit_name,edit_loadout,details,
                 visible_attributes=DEFAULT_BATTLE_ATTRIBUTE_KEYS,avatar_override=None):
        super().__init__();self.setObjectName('heroRow');self.wide=None
        extra = decode_extra_attributes(unit.get('attributes_raw'))
        potential = extra.get('potential_damage_modifier')
        self.heading_timer=QTimer(self);self.heading_timer.setSingleShot(True);self.heading_timer.timeout.connect(self.sync_heading_heights)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.root=QHBoxLayout(self);self.root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);self.root.setContentsMargins(3,1,3,1);self.root.setSpacing(3)
        identity=QWidget();identity.setObjectName('unitIdentity');identity.setFixedWidth(96)
        self.identity = identity
        left=QVBoxLayout(identity);left.setContentsMargins(0,0,0,0);left.setSpacing(4)
        top=QHBoxLayout();top.setSpacing(6)
        hero_id, hero_name = unit['hero_id'], unit['hero_name']
        suspected = suspected_hero_name(hero_id, hero_name)
        avatar=image_label('heroes',suspected or hero_name,28,avatar_override,hero_id=hero_id);top.addWidget(avatar)
        display_name = suspected or (f'#{hero_id}' if hero_name == f'角色 #{hero_id}' else hero_name)
        name=action(display_name,lambda:edit_name(unit));name.setObjectName('link')
        name.setMinimumWidth(0);name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        tooltip = f'编号 #{hero_id} · 编辑角色名称与头像'
        if suspected:
            tooltip = f'疑似{suspected}（编号末位相近）\n' + tooltip
        if avatar.pixmap().isNull():
            tooltip = f'{display_name} · 暂无头像\n' + tooltip
        avatar.setToolTip(tooltip)
        name.setToolTip(tooltip);top.addWidget(name,1)
        if potential == 10:
            name.setProperty('fullPotential', True)
            full_potential_badge(avatar)
        more=action('…',lambda:None);more.setObjectName('heroMore');more.setToolTip('角色详情与本场配装')
        menu=QMenu(more);menu.addAction('查看详情',lambda:details(unit));menu.addAction('修改本场配装',lambda:edit_loadout(unit))
        menu.addAction('编辑角色名称与头像', lambda:edit_name(unit))
        more.setMenu(menu);left.addLayout(top)
        if suspected:
            hint = text('疑似', 'hint')
            hint.setToolTip(tooltip)
            left.addWidget(hint)
        shell_names={s['name'] for s in unit.get('shells',[])}
        shell=(unit.get('manual') or {}).get('shell') or (next(iter(shell_names)) if len(shell_names)==1 else None)
        shellrow=QHBoxLayout();shellrow.setSpacing(5)
        if shell:shellrow.addWidget(image_label('shells',shell,24))
        shellname=text(shell or '智壳待识别','shell' if shell else 'hint');shellname.setWordWrap(False)
        shellname.setMinimumWidth(0);shellname.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        shellname.setToolTip(shell_text(unit));shellrow.addWidget(shellname,1);shellrow.addWidget(more);left.addLayout(shellrow)
        equipment=QVBoxLayout();equipment.setSpacing(2)
        manual=(unit.get('manual') or {}).get('matrices')
        matrices=manual if manual is not None else unit.get('matrix_effects_candidates',[])
        seen=set();unique=[]
        for m in matrices:
            threshold=m.get('points') if manual is not None else m.get('threshold')
            if (m['name'],threshold) in seen:continue
            seen.add((m['name'],threshold));unique.append((m,threshold))
        for m,threshold in unique[:3]:
            matrix=m['name'];group=QWidget();row=QHBoxLayout(group);row.setContentsMargins(0,0,0,0);row.setSpacing(4)
            row.addWidget(image_label('matrices',matrix,18))
            suffix=str(threshold) if threshold is not None else '?'
            if manual is not None:suffix+='*'
            elif m.get('confidence') not in ('已对照样本','用户映射'):suffix+='?'
            chip=text(f'<b style="color:{matrix_color(matrix)}">{escape(matrix)}</b> <span style="color:#a1afbd">{suffix}</span>','matrixName')
            chip.setTextFormat(Qt.TextFormat.RichText)
            chip.setToolTip(matrix_text(unit)+'\n'+imprint_text(unit)+'\n?：候选或档位未确认；*：本场手动。')
            chip.setAccessibleName('矩阵 '+matrix);row.addWidget(chip,1);equipment.addWidget(group)
        if not unique:equipment.addWidget(text('矩阵 —','hint'))
        if len(unique)>3:
            overflow=action('+'+str(len(unique)-3),lambda:details(unit));overflow.setObjectName('heroMore')
            overflow.setToolTip(matrix_text(unit));equipment.addWidget(overflow)
        left.addLayout(equipment);left.addStretch();self.root.addWidget(identity)
        attributes=QWidget();right=QVBoxLayout(attributes);right.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);right.setContentsMargins(0,0,0,0);right.setSpacing(1)
        self.basic=QGridLayout();self.basic.setHorizontalSpacing(3);self.basic.setVerticalSpacing(0)
        right.addLayout(self.basic)
        secondary=QFrame();secondary.setObjectName('extraAttributes');self.extra=QGridLayout(secondary);self.extra.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.extra.setContentsMargins(3,1,3,1);self.extra.setHorizontalSpacing(3);self.extra.setVerticalSpacing(0)
        right.addWidget(secondary)
        hints = component_hints(extra)
        if hints:
            hint = text('疑似元件  ' + ' · '.join(names for names, _ in hints), 'componentHint')
            hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            hint.setToolTip('\n'.join(f'{names} · {evidence}' for names, evidence in hints))
            right.addWidget(hint)
        right.addStretch();self.root.addWidget(attributes,1)
        base = [(key, title) for key, title in BASE_ATTRIBUTES if key in visible_attributes]
        secondary_attributes = [(key, title) for key, title in DAMAGE_ATTRIBUTES + SUPPORT_ATTRIBUTES
                                if key in visible_attributes]
        specs = base + secondary_attributes
        self.basic_count = len(base)
        self.attribute_keys = [key for key, _ in specs]
        secondary.setVisible(bool(secondary_attributes))
        self.cells=[]
        for index,(key,title) in enumerate(specs):
            is_extra = index >= self.basic_count
            is_percent = is_extra or key in BASE_PERCENT_KEYS
            values=extra if is_extra else unit.get('percent_attributes_tentative',{}) if is_percent else unit['stats']
            value=(values or {}).get(key)
            shown='—' if not isinstance(value,(int,float)) else f'{value:g}%' if is_percent else f'{value:.2f}' if key=='speed' else f'{value:g}'
            cell=QWidget();col=QBoxLayout(QBoxLayout.Direction.LeftToRight,cell)
            col.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);col.setContentsMargins(0,0,0,0);col.setSpacing(3 if is_extra else 0)
            # Headings may wrap; numeric values keep their actual font size.
            heading=text(title,'attributeTitle');heading.setWordWrap(True)
            policy=heading.sizePolicy();policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored);heading.setSizePolicy(policy)
            col.addWidget(heading)
            color = attribute_color(key, value)
            if key == 'speed' and color is not None and value > 405:
                metric = RainbowSpeed(shown)
            else:
                metric = text(shown, 'speed' if key == 'speed' else 'statValue')
                if color is not None:
                    metric.setStyleSheet(f'color: {color.name()};')
            metric.setWordWrap(False)
            metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}")
            if is_extra:metric.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            tip=title+'：'+shown+' · 对局开场已下发值；缺失不代表0，不再次叠加库存。'
            if key in ('pvp_damage_bonus','pvp_damage_reduction'):tip+=' 对局开场总值，已对照科技/元件同类合计。'
            if key=='extra_damage_reduction':tip+=' 命座与元件的额外减伤已计入此开场值。'
            if key=='damage_result_bonus':tip+=' 普通与相性增伤同区间；破序之刃10%等未下发条件值不补算。'
            metric.setToolTip(tip);col.addWidget(metric,1);self.cells.append(cell)
        self.reflow(False)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'heading_timer'):self.heading_timer.start(0)

    def sync_heading_heights(self):
        # Qt's nested height-for-width rounding can undershoot a QLabel by a
        # few pixels. Enforce its requirement at the final allocated width.
        changed=False
        for cell in self.cells:
            heading=cell.layout().itemAt(0).widget()
            required=max(0,heading.heightForWidth(heading.width()))
            if heading.minimumHeight()!=required:
                heading.setMinimumHeight(required);cell.layout().invalidate();cell.updateGeometry();changed=True
        if changed:
            self.basic.invalidate();self.extra.invalidate()
            self.basic.parentWidget().layout().invalidate()
            self.extra.parentWidget().updateGeometry();self.basic.parentWidget().updateGeometry()
            self.root.invalidate()
            self.setMinimumHeight(max(self.minimumSizeHint().height(),self.root.heightForWidth(self.width())+2*self.frameWidth()))
            self.updateGeometry()

    def reflow(self,wide,extra_columns=None,stack_basic=False,stack_extra=False,balanced=False):
        extra_columns=extra_columns or (6 if wide else 3)
        configuration=(wide,extra_columns,stack_basic,stack_extra,balanced)
        if getattr(self,'configuration',None)==configuration:return
        self.configuration=configuration;self.wide=wide
        for index,cell in enumerate(self.cells):
            # Percentage labels and values are both long with Windows CJK
            # fonts. Stacking them also in compact mode prevents their summed
            # minimum widths from forcing both teams beyond the viewport.
            stacked=(wide or stack_basic or self.attribute_keys[index] in BASE_PERCENT_KEYS) if index<self.basic_count else stack_extra
            heading=cell.layout().itemAt(0).widget()
            # An inline label must reserve its text width before the numeric
            # value claims space. Ignored size policy otherwise permits zero.
            policy=heading.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored if stacked else QSizePolicy.Policy.Preferred)
            heading.setSizePolicy(policy)
            heading.setMinimumWidth(0 if stacked else heading.sizeHint().width())
            cell.layout().setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
            cell.layout().setSpacing(0 if stacked else 3)
            cell.layout().invalidate();cell.updateGeometry()
        for layout in (self.basic,self.extra):
            while layout.count():layout.takeAt(0)
            for column in range(8):layout.setColumnStretch(column,0)
        basic_order=sorted(range(self.basic_count),key=lambda i:self.cells[i].layout().itemAt(1).widget().minimumWidth(),reverse=True) if balanced else []
        for index,cell in enumerate(self.cells):
            is_basic = index < self.basic_count
            grid=self.basic if is_basic else self.extra;i=index if is_basic else index-self.basic_count
            columns=(8 if wide else 4) if is_basic else extra_columns
            if is_basic and balanced and self.basic_count > columns:
                position=basic_order.index(index);grid.addWidget(cell,position%2,position//2)
            else:grid.addWidget(cell,i//columns,i%columns)
        # Recompute from the cells upward before testing the new minimum.
        # Otherwise QWidgetItem caches can still describe the previous grid.
        self.basic.invalidate();self.extra.invalidate()
        self.extra.parentWidget().updateGeometry()
        attributes=self.basic.parentWidget()
        attributes.layout().invalidate();attributes.updateGeometry()
        self.root.invalidate();self.updateGeometry()

    def fit_width(self,width):
        # Use the viewport's allotted team width, never our current width:
        # the wide grid's minimum can otherwise prevent a shrinking window
        # from delivering a smaller resize event to this card.
        self.ensurePolished()
        self.setMinimumWidth(0)
        self.identity.setFixedWidth(96)
        for cell in self.cells:
            for widget in cell.findChildren(QWidget):
                widget.ensurePolished()
                if widget.objectName()=='attributeTitle':widget.setMinimumHeight(0)
                if widget.objectName() in ('statValue','speed'):
                    # Wrapping headers must never squeeze the value's height
                    # or width below what the polished font requires.
                    widget.setMinimumSize(widget.sizeHint())
            cell.setMinimumSize(0,0);cell.layout().invalidate();cell.updateGeometry()
        # Compare the actual polished minimum sizes. Different fonts can make
        # either grid the limiting width; choose the shortest arrangement that
        # fits, rather than adding rows when stacking labels is sufficient.
        candidates=([(True,6,False,False)] if width>=900 else [])+[
            (False,3,False,False),(False,2,False,False),
            (False,3,True,False),(False,2,True,False),
            (False,3,False,True),(False,3,True,True),
            (False,2,False,True),(False,2,True,True),
            (False,3,True,True,True),(False,2,True,True,True)]
        if len(self.cells) - self.basic_count > 6:
            candidates.extend(((False,4,False,True),(False,4,True,True),(False,4,True,True,True)))
        fitting=[];measured=[]
        for priority,configuration in enumerate(candidates):
            self.reflow(*configuration)
            for cell in self.cells:cell.layout().activate()
            self.basic.parentWidget().layout().activate();self.root.invalidate()
            size=self.minimumSizeHint()
            # A wrapping layout can be much taller than minimumSizeHint.
            # Rank candidates at the width they will actually receive.
            height=self.root.heightForWidth(width)
            if height>=0:size.setHeight(max(size.height(),height))
            measured.append((size.width(),size.height(),priority,configuration))
            if size.width()<=width:fitting.append((size.height(),priority,configuration))
        configuration = min(fitting)[2] if fitting else min(measured)[3]
        self.reflow(*configuration)
        if fitting and width >= 550 and not any(configuration[2:4]):
            # Leave extra room for equipment names after fitting the stat grid.
            spare = width - self.minimumSizeHint().width()
            self.identity.setFixedWidth(96 + min(48 if width >= 730 else 32, max(0, spare)))
        height=self.root.heightForWidth(width)
        self.setMinimumHeight(max(self.minimumSizeHint().height(),height+2*self.frameWidth()))
        self.heading_timer.start(0)


def unit_card(unit,team,action,edit_name,edit_loadout,details,
              visible_attributes=DEFAULT_BATTLE_ATTRIBUTE_KEYS,avatar_override=None):
    return UnitCard(unit,team,action,edit_name,edit_loadout,details,visible_attributes,avatar_override)

