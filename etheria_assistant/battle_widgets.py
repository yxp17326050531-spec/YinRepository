"""Readable compact battle rows. Pictures supplement the full text labels."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout
from artwork import image_label,matrix_color
from capture import shell_text,matrix_text,imprint_text
from battle_attributes import decode_extra_attributes,pending_attributes


def text(value,name=None):
    w=QLabel(value);w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText)
    if name:w.setObjectName(name)
    return w


def unit_card(unit,team,action,edit_name,edit_loadout,details):
    card=QFrame();card.setObjectName('heroRow')
    root=QVBoxLayout(card);root.setContentsMargins(5,13,5,13);root.setSpacing(10)
    top=QHBoxLayout();top.setSpacing(10)
    top.addWidget(image_label('heroes',unit['hero_name'],48))
    name=action(unit['hero_name'],lambda:edit_name(unit));name.setObjectName('link')
    name.setToolTip('点击修改名称 · #'+str(unit['hero_id']));top.addWidget(name,1)
    for title,fn in [('配装',edit_loadout),('详情',details)]:
        b=action(title,lambda f=fn:f(unit));b.setObjectName('smallAction');top.addWidget(b)
    root.addLayout(top)
    body=QHBoxLayout();body.setSpacing(12)
    attributes=QWidget();attributes.setFixedWidth(328)
    grid=QGridLayout(attributes);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(8);grid.setVerticalSpacing(8)
    specs=[('hp','生命'),('attack','攻击'),('defense','防御'),('speed','速度'),
           ('crit','暴击率'),('crit_damage','暴击伤害'),('effect_hit','效果命中'),('effect_resist','效果抵抗'),
           ('pvp_damage_bonus','PVP增伤'),('pvp_damage_reduction','PVP减伤'),('extra_damage_reduction','额外减伤'),('ignore_defense','无视防御'),
           ('damage_result_bonus','结果增伤'),('damage_result_reduction','结果减伤')]
    extra=decode_extra_attributes(unit.get('attributes_raw'))
    for index,(key,title) in enumerate(specs):
        values=extra if index>=8 else unit.get('percent_attributes_tentative',{}) if index>=4 else unit['stats']
        value=(values or {}).get(key)
        shown='—' if not isinstance(value,(int,float)) else f'{value:g}%' if index>=4 else f'{value:.2f}' if key=='speed' else f'{value:g}'
        cell=QWidget();cell.setFixedWidth(76);col=QVBoxLayout(cell);col.setContentsMargins(0,0,0,0);col.setSpacing(1)
        heading=text(title,'attributeTitle');heading.setWordWrap(False);col.addWidget(heading)
        metric=text(shown,'speed' if key=='speed' else 'statValue');metric.setWordWrap(False)
        metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}")
        tip=title+'：'+shown+' · 对局开场已下发值；缺失不代表0，不再次叠加库存。'
        if key in ('pvp_damage_bonus','pvp_damage_reduction'):tip+=' 对局开场总值，已对照科技/元件同类合计。'
        if key=='extra_damage_reduction':tip+=' 潜能与涌泉效果分开，不按矩阵说明改写。'
        if key=='damage_result_bonus':tip+=' 普通与相性增伤同区间；破序之刃10%等未下发条件值不补算。'
        metric.setToolTip(tip);col.addWidget(metric);grid.addWidget(cell,index//4,index%4)
    body.addWidget(attributes)
    equipment=QWidget();equipment.setMinimumWidth(155);eq=QVBoxLayout(equipment);eq.setContentsMargins(0,0,0,0);eq.setSpacing(7)
    shell_names={s['name'] for s in unit.get('shells',[])}
    shell=(unit.get('manual') or {}).get('shell') or (next(iter(shell_names)) if len(shell_names)==1 else None)
    shellrow=QHBoxLayout();shellrow.setSpacing(7)
    if shell:shellrow.addWidget(image_label('shells',shell,32))
    shellname=text(shell_text(unit),'shell');shellname.setToolTip(shell_text(unit));shellrow.addWidget(shellname,1);eq.addLayout(shellrow)
    manual=(unit.get('manual') or {}).get('matrices')
    matrices=manual if manual is not None else unit.get('matrix_effects_candidates',[])
    seen=set()
    for m in matrices:
        name=m['name'];threshold=m.get('points') if manual is not None else m.get('threshold')
        if (name,threshold) in seen:continue
        seen.add((name,threshold))
        row=QHBoxLayout();row.setSpacing(6);row.addWidget(image_label('matrices',name,24))
        suffix=f'+{threshold}' if manual is not None else f'{threshold}点' if threshold is not None else '档位待确认'
        if manual is not None:suffix+=' · 手动'
        elif m.get('confidence') not in ('已对照样本','用户映射'):suffix+=' · 候选'
        chip=text(f'<b style="color:{matrix_color(name)}">{escape(name)}</b> <span style="color:#a1afbd">{suffix}</span>','matrixName')
        chip.setTextFormat(Qt.TextFormat.RichText)
        chip.setToolTip(matrix_text(unit));chip.setAccessibleName('矩阵 '+name);row.addWidget(chip,1);eq.addLayout(row)
    if not matrices:eq.addWidget(text('完整矩阵未知','hint'))
    eq.addWidget(text(imprint_text(unit),'hint'));eq.addStretch()
    hint=text('更多属性 · 详情','hint');pending=pending_attributes(unit)
    hint.setToolTip('原始属性未保存' if pending is None else f'另有 {len(pending)} 项属性待对照；开场值不保证包含条件技能效果。')
    eq.addWidget(hint);body.addWidget(equipment,1);root.addLayout(body)
    card.ensurePolished();root.invalidate();card.setMinimumHeight(card.sizeHint().height())
    return card
