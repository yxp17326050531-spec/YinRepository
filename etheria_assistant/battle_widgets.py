"""Responsive Qt battle rows, with identity and two distinct attribute groups."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QMenu,QSizePolicy,QBoxLayout
from artwork import image_label,matrix_color
from capture import shell_text,matrix_text,imprint_text
from battle_attributes import decode_extra_attributes


def text(value,name=None):
    w=QLabel(value);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText)
    if name:w.setObjectName(name)
    return w


class UnitCard(QFrame):
    """Reflow actual Qt layouts; all fourteen values remain visible at either width."""
    def __init__(self,unit,team,action,edit_name,edit_loadout,details):
        super().__init__();self.setObjectName('heroRow');self.wide=None
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.root=QHBoxLayout(self);self.root.setContentsMargins(4,2,4,2);self.root.setSpacing(4)
        identity=QWidget();identity.setObjectName('unitIdentity');identity.setFixedWidth(112)
        left=QVBoxLayout(identity);left.setContentsMargins(0,0,0,0);left.setSpacing(4)
        top=QHBoxLayout();top.setSpacing(6);top.addWidget(image_label('heroes',unit['hero_name'],28))
        name=action(unit['hero_name'],lambda:edit_name(unit));name.setObjectName('link')
        name.setMinimumWidth(0);name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        name.setToolTip(unit['hero_name']+' · 修改精确编号名称 #'+str(unit['hero_id']));top.addWidget(name,1)
        more=action('⋯',lambda:None);more.setObjectName('heroMore');more.setToolTip('角色详情与本场配装')
        menu=QMenu(more);menu.addAction('查看详情',lambda:details(unit));menu.addAction('修改本场配装',lambda:edit_loadout(unit))
        more.setMenu(menu);left.addLayout(top)
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
        attributes=QWidget();right=QVBoxLayout(attributes);right.setContentsMargins(0,0,0,0);right.setSpacing(2)
        self.basic=QGridLayout();self.basic.setHorizontalSpacing(3);self.basic.setVerticalSpacing(1)
        right.addLayout(self.basic)
        secondary=QFrame();secondary.setObjectName('extraAttributes');self.extra=QGridLayout(secondary)
        self.extra.setContentsMargins(3,1,3,1);self.extra.setHorizontalSpacing(3);self.extra.setVerticalSpacing(1)
        right.addWidget(secondary);right.addStretch();self.root.addWidget(attributes,1)
        specs=[('hp','生命'),('attack','攻击'),('defense','防御'),('speed','速度'),
               ('crit','暴击率'),('crit_damage','暴击伤害'),('effect_hit','效果命中'),('effect_resist','效果抵抗'),
               ('pvp_damage_bonus','PVP增伤'),('damage_result_bonus','结果增伤'),('ignore_defense','无视防御'),
               ('pvp_damage_reduction','PVP减伤'),('damage_result_reduction','结果减伤'),('extra_damage_reduction','额外减伤')]
        extra=decode_extra_attributes(unit.get('attributes_raw'));self.cells=[]
        for index,(key,title) in enumerate(specs):
            values=extra if index>=8 else unit.get('percent_attributes_tentative',{}) if index>=4 else unit['stats']
            value=(values or {}).get(key)
            shown='—' if not isinstance(value,(int,float)) else f'{value:g}%' if index>=4 else f'{value:.2f}' if key=='speed' else f'{value:g}'
            cell=QWidget();col=QBoxLayout(QBoxLayout.Direction.LeftToRight,cell)
            col.setContentsMargins(0,0,0,0);col.setSpacing(3 if index>=8 else 0)
            heading=text(title,'attributeTitle');heading.setWordWrap(False);col.addWidget(heading)
            metric=text(shown,'speed' if key=='speed' else 'statValue');metric.setWordWrap(False)
            metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}")
            if index>=8:metric.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            tip=title+'：'+shown+' · 对局开场已下发值；缺失不代表0，不再次叠加库存。'
            if key in ('pvp_damage_bonus','pvp_damage_reduction'):tip+=' 对局开场总值，已对照科技/元件同类合计。'
            if key=='extra_damage_reduction':tip+=' 潜能与涌泉效果分开，不按矩阵说明改写。'
            if key=='damage_result_bonus':tip+=' 普通与相性增伤同区间；破序之刃10%等未下发条件值不补算。'
            metric.setToolTip(tip);col.addWidget(metric,1);self.cells.append(cell)
        self.reflow(False)

    def reflow(self,wide):
        if self.wide==wide:return
        self.wide=wide
        for index,cell in enumerate(self.cells[:8]):
            # Percentage labels and values are both long with Windows CJK
            # fonts. Stacking them also in compact mode prevents their summed
            # minimum widths from forcing both teams beyond the viewport.
            stacked=wide or index>=4
            cell.layout().setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
            cell.layout().setSpacing(0 if stacked else 3)
            cell.layout().invalidate();cell.updateGeometry()
        for layout in (self.basic,self.extra):
            while layout.count():layout.takeAt(0)
            for column in range(8):layout.setColumnStretch(column,0)
        for index,cell in enumerate(self.cells):
            grid=self.basic if index<8 else self.extra;i=index if index<8 else index-8
            columns=(8 if wide else 4) if index<8 else (6 if wide else 3)
            grid.addWidget(cell,i//columns,i%columns)
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
        self.reflow(width>=900)
        if self.wide and self.minimumSizeHint().width()>width:
            self.reflow(False)


def unit_card(unit,team,action,edit_name,edit_loadout,details):
    return UnitCard(unit,team,action,edit_name,edit_loadout,details)
