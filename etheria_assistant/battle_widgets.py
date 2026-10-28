"""Responsive Qt battle rows, with identity and two distinct attribute groups."""
from html import escape
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QMenu,QSizePolicy,QBoxLayout,QLayout
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
        self.heading_timer=QTimer(self);self.heading_timer.setSingleShot(True);self.heading_timer.timeout.connect(self.sync_heading_heights)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        self.root=QHBoxLayout(self);self.root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);self.root.setContentsMargins(3,1,3,1);self.root.setSpacing(3)
        identity=QWidget();identity.setObjectName('unitIdentity');identity.setFixedWidth(96)
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
        attributes=QWidget();right=QVBoxLayout(attributes);right.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);right.setContentsMargins(0,0,0,0);right.setSpacing(1)
        self.basic=QGridLayout();self.basic.setHorizontalSpacing(3);self.basic.setVerticalSpacing(0)
        right.addLayout(self.basic)
        secondary=QFrame();secondary.setObjectName('extraAttributes');self.extra=QGridLayout(secondary);self.extra.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.extra.setContentsMargins(3,1,3,1);self.extra.setHorizontalSpacing(3);self.extra.setVerticalSpacing(0)
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
            col.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint);col.setContentsMargins(0,0,0,0);col.setSpacing(3 if index>=8 else 0)
            # Headings may wrap; numeric values keep their actual font size.
            heading=text(title,'attributeTitle');heading.setWordWrap(True)
            policy=heading.sizePolicy();policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored);heading.setSizePolicy(policy)
            col.addWidget(heading)
            metric=text(shown,'speed' if key=='speed' else 'statValue');metric.setWordWrap(False)
            metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}")
            if index>=8:metric.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            tip=title+'：'+shown+' · 对局开场已下发值；缺失不代表0，不再次叠加库存。'
            if key in ('pvp_damage_bonus','pvp_damage_reduction'):tip+=' 对局开场总值，已对照科技/元件同类合计。'
            if key=='extra_damage_reduction':tip+=' 潜能与涌泉效果分开，不按矩阵说明改写。'
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
            self.setMinimumHeight(max(self.root.minimumSize().height(),self.root.heightForWidth(self.width())))
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
            stacked=(wide or stack_basic or index>=4) if index<8 else stack_extra
            cell.layout().setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
            cell.layout().setSpacing(0 if stacked else 3)
            cell.layout().invalidate();cell.updateGeometry()
        for layout in (self.basic,self.extra):
            while layout.count():layout.takeAt(0)
            for column in range(8):layout.setColumnStretch(column,0)
        basic_order=sorted(range(8),key=lambda i:self.cells[i].layout().itemAt(1).widget().minimumWidth(),reverse=True) if balanced else list(range(8))
        for index,cell in enumerate(self.cells):
            grid=self.basic if index<8 else self.extra;i=index if index<8 else index-8
            columns=(8 if wide else 4) if index<8 else extra_columns
            if index<8 and balanced:
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
        self.reflow(*(min(fitting)[2] if fitting else min(measured)[3]))
        height=self.root.heightForWidth(width)
        self.setMinimumHeight(max(self.root.minimumSize().height(),height))
        self.heading_timer.start(0)


def unit_card(unit,team,action,edit_name,edit_loadout,details):
    return UnitCard(unit,team,action,edit_name,edit_loadout,details)

