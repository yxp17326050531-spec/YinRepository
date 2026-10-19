"""Compact battle cards: fourteen attributes and equipment at a glance."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QMenu
from artwork import image_label,matrix_color
from capture import shell_text,matrix_text,imprint_text
from battle_attributes import decode_extra_attributes


def text(value,name=None):
    w=QLabel(value);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText)
    if name:w.setObjectName(name)
    return w


def unit_card(unit,team,action,edit_name,edit_loadout,details):
    card=QFrame();card.setObjectName('heroRow')
    root=QVBoxLayout(card);root.setContentsMargins(4,1,4,1);root.setSpacing(2)
    top=QHBoxLayout();top.setSpacing(7)
    top.addWidget(image_label('heroes',unit['hero_name'],28))
    name=action(unit['hero_name'],lambda:edit_name(unit));name.setObjectName('link')
    name.setToolTip('修改精确编号名称 · #'+str(unit['hero_id']));top.addWidget(name,1)
    shell_names={s['name'] for s in unit.get('shells',[])}
    shell=(unit.get('manual') or {}).get('shell') or (next(iter(shell_names)) if len(shell_names)==1 else None)
    if shell:
        top.addWidget(image_label('shells',shell,24));shellname=text(shell,'shell');shellname.setWordWrap(False)
    else:shellname=text('智壳待识别','hint')
    shellname.setToolTip(shell_text(unit));top.addWidget(shellname)
    more=action('⋯',lambda:None);more.setObjectName('heroMore');more.setToolTip('角色详情与本场配装')
    menu=QMenu(more)
    menu.addAction('查看详情',lambda:details(unit));menu.addAction('修改本场配装',lambda:edit_loadout(unit))
    more.setMenu(menu);top.addWidget(more);root.addLayout(top)
    attributes=QWidget();grid=QGridLayout(attributes);grid.setContentsMargins(0,0,0,0)
    grid.setHorizontalSpacing(5);grid.setVerticalSpacing(2)
    # Inline names and values keep fourteen attributes readable in three rows.
    specs=[('hp','生命'),('attack','攻击'),('defense','防御'),('speed','速度'),
           ('crit','暴击率'),('crit_damage','暴击伤害'),('effect_hit','效果命中'),('effect_resist','效果抵抗'),
           ('pvp_damage_bonus','PVP增伤'),('pvp_damage_reduction','PVP减伤'),('extra_damage_reduction','额外减伤'),('ignore_defense','无视防御'),
           ('damage_result_bonus','结果增伤'),('damage_result_reduction','结果减伤')]
    extra=decode_extra_attributes(unit.get('attributes_raw'))
    for index,(key,title) in enumerate(specs):
        values=extra if index>=8 else unit.get('percent_attributes_tentative',{}) if index>=4 else unit['stats']
        value=(values or {}).get(key)
        shown='—' if not isinstance(value,(int,float)) else f'{value:g}%' if index>=4 else f'{value:.2f}' if key=='speed' else f'{value:g}'
        cell=QWidget();col=QHBoxLayout(cell);col.setContentsMargins(0,0,0,0);col.setSpacing(4)
        heading=text(title,'attributeTitle');heading.setWordWrap(False);col.addWidget(heading)
        metric=text(shown,'speed' if key=='speed' else 'statValue');metric.setWordWrap(False)
        metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}");metric.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        tip=title+'：'+shown+' · 对局开场已下发值；缺失不代表0，不再次叠加库存。'
        if key in ('pvp_damage_bonus','pvp_damage_reduction'):tip+=' 对局开场总值，已对照科技/元件同类合计。'
        if key=='extra_damage_reduction':tip+=' 潜能与涌泉效果分开，不按矩阵说明改写。'
        if key=='damage_result_bonus':tip+=' 普通与相性增伤同区间；破序之刃10%等未下发条件值不补算。'
        metric.setToolTip(tip);col.addWidget(metric,1);grid.addWidget(cell,index//5,index%5)
    root.addWidget(attributes)
    equipment=QHBoxLayout();equipment.setSpacing(8)
    manual=(unit.get('manual') or {}).get('matrices')
    matrices=manual if manual is not None else unit.get('matrix_effects_candidates',[])
    seen=set();unique=[]
    for m in matrices:
        threshold=m.get('points') if manual is not None else m.get('threshold')
        if (m['name'],threshold) in seen:continue
        seen.add((m['name'],threshold));unique.append((m,threshold))
    for m,threshold in unique[:3]:
        name=m['name'];group=QWidget();row=QHBoxLayout(group);row.setContentsMargins(0,0,0,0);row.setSpacing(4)
        row.addWidget(image_label('matrices',name,18))
        suffix=str(threshold) if threshold is not None else '?'
        if manual is not None:suffix+='*'
        elif m.get('confidence') not in ('已对照样本','用户映射'):suffix+='?'
        chip=text(f'<b style="color:{matrix_color(name)}">{escape(name)}</b> <span style="color:#a1afbd">{suffix}</span>','matrixName')
        chip.setTextFormat(Qt.TextFormat.RichText);chip.setWordWrap(False)
        chip.setToolTip(matrix_text(unit)+'\n'+imprint_text(unit)+'\n?：候选或档位未确认；*：本场手动。')
        chip.setAccessibleName('矩阵 '+name);row.addWidget(chip);equipment.addWidget(group)
    if not unique:equipment.addWidget(text('矩阵 —','hint'))
    if len(unique)>3:
        overflow=action('+'+str(len(unique)-3),lambda:details(unit));overflow.setObjectName('heroMore')
        overflow.setToolTip(matrix_text(unit));equipment.addWidget(overflow)
    equipment.addStretch();root.addLayout(equipment)
    card.ensurePolished();root.invalidate();card.setMinimumHeight(card.sizeHint().height())
    return card
