"""Compact native calculator grouping; widgets and calculation state stay owned by dialog."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,QGroupBox,QPushButton,QLabel,QCheckBox,QLineEdit


def simplify_calculator(d):
    # Existing objects/signals remain intact; replace only presentation containers.
    d._legacy_pages=[]
    def page(index,title):
        old=d.tabs.widget(index);d.tabs.removeTab(index);old.hide();old.setParent(d);d._legacy_pages.append(old)
        w=QWidget();layout=QVBoxLayout(w);layout.setSpacing(12)
        from PySide6.QtWidgets import QScrollArea
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(w)
        d.tabs.insertTab(index,scroll,title)
        return layout
    def group(parent,title,rows,fold=False):
        box=QGroupBox(title);outer=QVBoxLayout(box);content=QWidget();form=QFormLayout(content)
        form.setSpacing(9)
        for label,w in rows:
            w.setParent(content)
            if label:form.addRow(label,w)
            else:form.addRow(w)
        if fold:
            toggle=QPushButton('展开');toggle.setCheckable(True);outer.addWidget(toggle)
            toggle.toggled.connect(content.setVisible)
            toggle.toggled.connect(lambda checked:toggle.setText('收起' if checked else '展开'))
            content.hide()
            # Expose selected values in folded groups so effects aren't silently hidden.
            summary=QLabel();summary.setWordWrap(True);outer.addWidget(summary)
            def update(*_):
                active=[]
                for label,w in rows:
                    if isinstance(w,QCheckBox):
                        if w.isChecked():active.append(w.text())
                    elif hasattr(w,'currentData') and w.currentData():active.append((label or '')+' '+w.currentText())
                    elif hasattr(w,'value') and w.value()>0:active.append((label or '')+' '+str(w.value()))
                    elif isinstance(w,QLineEdit) and w.text():active.append((label or '')+' '+w.text())
                summary.setText(' · '.join(active) if active else '按需展开设置')
            for _,w in rows:
                if isinstance(w,QCheckBox):w.toggled.connect(update)
                elif hasattr(w,'currentIndexChanged'):w.currentIndexChanged.connect(update)
                elif hasattr(w,'valueChanged'):w.valueChanged.connect(update)
                elif hasattr(w,'textChanged'):w.textChanged.connect(update)
            update()
        outer.addWidget(content);parent.addWidget(box)
        return box
    def rows(*pairs):return [(label,getattr(d,key)) for label,key in pairs]
    shorter={'durand':'攻击增加48%','crit50':'暴伤增加50个百分点','magic':'魔术牌30%',
        'harvest':'收割 · 高于半血穿防40%','fury':'狂怒 · 暴击×1.12','boiling':'沸腾打击',
        'insight':'洞悉穿刺 · 25% / 15% / 5%','opportunist':'乘势追击','desecrate':'亵渎 · 有盾增伤',
        'bloodbath':'浴血之躯','spring':'涌泉','unyielding':'不屈之誓',
        'critical':'每段暴击','pvp':'PVP模式','controlled':'宝剑七控制增伤已触发'}
    for key,text in shorter.items():
        w=getattr(d,key);w.setToolTip(w.text());w.setText(text)
    panel=page(0,'双方面板');cols=QHBoxLayout();panel.addLayout(cols)
    from damage_calculator_widgets import LABELS
    for role,title in [('attacker','攻方'),('defender','守方')]:
        col=QVBoxLayout();cols.addLayout(col,1)
        basic=[(LABELS[k],d.fields[role][k]) for k in ('attack','hp','defense','crit','crit_damage')]
        if role=='attacker':basic.append(('白字基础攻击',d.base_attack))
        group(col,title+' · 基础',basic)
        keys=('pvp_damage_bonus','ignore_defense','damage_result_bonus') if role=='attacker' else ('pvp_damage_reduction','extra_damage_reduction','damage_result_reduction')
        group(col,title+' · 常用增减伤',[(LABELS[k],d.fields[role][k]) for k in keys])
        rest=[(LABELS[k],w) for k,w in d.fields[role].items() if k not in {'attack','hp','defense','crit','crit_damage',*keys}]
        group(col,title+' · 条件属性',rest,True)
        group(col,'导入来源 / 未套用属性',[('',d.source_labels[role])],True);col.addStretch()
    skill=page(1,'技能与增益');cols=QHBoxLayout();skill.addLayout(cols);left=QVBoxLayout();right=QVBoxLayout();cols.addLayout(left,1);cols.addLayout(right,1)
    group(left,'角色与技能',rows(('角色模板','preset'),('技能','character_skill'),('','critical'),('','pvp'),('相性关系','affinity')))
    d.character_note.setToolTip('角色技能规则与研究假设；展开查看。')
    params=group(left,'角色专属参数',rows(('','character_panels')))
    def show_parameters(*_):params.setVisible(d.preset.currentText() not in ('魁洛','自定义技能'))
    d.preset.currentIndexChanged.connect(show_parameters);show_parameters()
    group(left,'技能说明',rows(('','character_note')),True)
    group(right,'攻方 · 常用增益',rows(('','durand'),('','crit50'),('','magic'),('攻击增加 %','attack_up'),('暴伤增加 %','crit_damage_up'),('相性增伤补录 %','manual_attribute_bonus')))
    group(right,'攻方 · 其他修正',rows(('攻击降低 %','attack_down'),('旧花种入口','flower'),('其他乘数','damage_multiplier')),True)
    left.addStretch();right.addStretch()
    # Statuses keep both sides visible, grouped by purpose instead of one long mixed list.
    statuses=page(3,'角色状态')
    from calculator_statuses import STATUSES
    categories=[('常用增益与减益',{'defense','weak','vulnerable','speed_up','speed_down','flower','sun','heart','dataflow'}),
        ('保护与减伤',{'tiamat','guard','threat','color','jade','scales','paper','shield'}),
        ('特殊状态 / 预留入口',{'void','lin','execution','frost','nightmare','rain','feather','lastwords','sleep'})]
    for title,keys in categories:
        box=QGroupBox(title);grid=QGridLayout(box);grid.addWidget(QLabel('效果'),0,0);grid.addWidget(QLabel('攻方'),0,1);grid.addWidget(QLabel('守方'),0,2)
        n=1
        for key,name,description,*_ in STATUSES:
            if key not in keys:continue
            label=QLabel(name);label.setWordWrap(True);label.setToolTip(description);grid.addWidget(label,n,0)
            for i,role in enumerate(('attacker','defender'),1):
                w=d.status_states[role][key];w.setParent(box);grid.addWidget(w,n,i)
            n+=1
        statuses.addWidget(box)
    statuses.addStretch()
    equipment=page(4,'装备效果');cols=QHBoxLayout();equipment.addLayout(cols);a=QVBoxLayout();b=QVBoxLayout();cols.addLayout(a,1);cols.addLayout(b,1)
    group(a,'攻方 · 矩阵',rows(('','harvest'),('','fury'),('','boiling'),('','insight'),('','opportunist'),('目标减益种类','debuff_count'),('','desecrate')))
    group(a,'攻方 · 智壳',rows(('智壳','shell'),('','shell_status'),('伯爵算法','count_version'),('噬身之蛇层数','serpent'),('白獠暴伤层数','white_stacks'),('','controlled')))
    group(b,'攻方 · 屠夫',rows(('增伤档位','butcher_tier'),('当前生命 %','attacker_hp_percent')))
    group(b,'守方 · 矩阵与刻影',rows(('','bloodbath'),('','spring'),('','unyielding'),('戍防官（仅暴击）','warden_tier'),('','warden_not_in_panel')))
    group(b,'守方 · 当前血量与护盾',rows(('当前生命','remaining_hp'),('浴血本回合已扣血','bloodbath_spent'),('护盾剩余量','shield_remaining')))
    a.addStretch();b.addStretch()
    advanced=page(5,'高级设置')
    group(advanced,'自定义技能 / 公式',rows(('防御模型','model'),('缩放属性','scaling'),('段数','hits'),('每段倍率 %','ratio'),('不同段倍率 %','ratios'),('主目标乘数','target_multiplier'),('','quilo_passive'),('','aoe'),('','secondary')),True)
    group(advanced,'守方防御变化',rows(('防御增加 %','defense_up'),('防御降低 %','defense_down'),('固定减防','flat_defense_down'),('攻方额外穿防 %','other_ignore')),True)
    group(advanced,'洞悉 / 日轮花参数',rows(('此前伤害次数','prior_events'),('每段计次（默认1）','insight_events'),('日轮基础增伤 %','sun_base_bonus'),('每种新增增益 %','sun_per_buff_bonus')),True)
    advanced.addStretch()
    d.tabs.setTabText(2,'计算结果');d.tabs.setCurrentIndex(1)
    d.base_attack.setToolTip('游戏面板白字攻击，不是白字+绿字总攻击。三角色提供截图参考值，可修改并随攻方预设保存。')
