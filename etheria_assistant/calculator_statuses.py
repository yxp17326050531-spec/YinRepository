"""Screenshot-transcribed choices; unsupported mechanics block estimates explicitly."""
from dataclasses import replace

# key, name, description, state count, supported
STATUSES = [
 ('void','虚无','抵抗+80%；无法被选主目标，群体承伤-70%；需在条件页确认群体及次目标',1,True),
 ('tiamat','提亚马特保护·分摊','用户确认按最终伤害减少25%；不模拟分摊者生命',1,True),
 ('guard','丹弗里·防卫','受到的伤害额外降低30%',1,True),
 ('defense','防御上升','防御提升60%',1,True),
 ('threat','威胁','受到的伤害额外降低30%；抵抗和选目标不参与伤害试算',1,True),
 ('lin','麟佑','每次格挡施加者防御110%，最低剩原伤害20%；格挡后自疗50%，需完整结算模型',1,False),
 ('execution','行刑式·入场500防档数','技能5级：每500入场防御增伤8%、减伤6%；档数需手动确认，取整与上限待验证',30,True),
 ('color','彩佑','按当前增益数量：每个承伤减少10%，最多5个',5,True),
 ('weak','虚弱','造成的伤害额外减少25%',1,True),
 ('vulnerable','易伤','受到伤害提升30%',1,True),
 ('frost','霜花','造成伤害提升25%；吸收伤害部分需另填护盾量',1,True),
 ('speed_down','速度下降','速度降低30%；本计算器未实现速度缩放技能，不直接改伤害',1,True),
 ('speed_up','速度上升','速度提升30%；本计算器未实现速度缩放技能，不直接改伤害',1,True),
 ('heart','心火','每次进化：攻击+25%、暴伤+15个百分点、受到伤害降低18%，最多3次',3,True),
 ('nightmare','梦魇（截图名称梦魔）','受到伤害提升15%；治疗攻击者15%，攻击者生命未模拟',1,True),
 ('shield','护盾','条件页填写剩余吸收量；暂不与浴血组合',1,True),
 ('rain','雨幕','吸收50%伤害、反射吸收量100%；需剩余容量及施加者信息',1,False),
 ('flower','瑠花种 / 明花彩','1/2层各加6%攻防速；第3层转换为明花彩，攻防速+30%',3,True),
 ('jade','寒玉','受到伤害额外降低40%；每次攻击类技能消耗1层，最多5层',5,True),
 ('feather','逆羽','每层承伤提升6%、速度下降3点，最多10层',10,True),
 ('lastwords','遗言','每层被暴击伤害和概率提升7%，最多4层；暴击概率不参与确定性试算',4,True),
 ('dataflow','数据流','每层造成伤害+3.5%、速度+3点，最多12层',12,True),
 ('sleep','睡眠','本次受伤额外+25%，受伤后解除；按首个伤害段解除的研究假设',1,True),
 ('sun','日轮花','增伤数值在条件页填写；与魔术牌同区加算。选择持续期间新获得的不同基础增益0–5种；减伤仍为20%',6,True),
 ('scales','化鳞（技能5级）','全队被暴击伤害降低30%；反击不参与单次输出试算',1,True),
 ('paper','纸人守护','攻击类技能消耗1层，使本次承伤降低35%；按整次技能生效假设，最多5层',5,True),
]


def apply_statuses(s, attack_states, defense_states):
    """Different named modifiers multiply except the user-confirmed card/sun group.

    Inputs are current states, not automatic battle lifecycle predictions.
    """
    by_key = {r[0]: r for r in STATUSES}
    for states in (attack_states, defense_states):
        for key, layers in states.items():
            row = by_key[key]
            if not isinstance(layers,int) or not 0 <= layers <= row[3]:
                raise ValueError('状态层数超出范围：'+row[1])
            if layers and not row[4]:
                raise ValueError(row[1]+'已保留选择项，但尚不能可靠结算：'+row[2])
    if defense_states.get('shield') and s.shield_hp <= 0:
        raise ValueError('护盾需要剩余吸收量')
    def flower(states):
        n=states.get('flower',0)
        return 30 if n==3 else 6*n
    a,d = s.attacker,s.defender
    attack_up=s.attack_up + 25*attack_states.get('heart',0)+flower(attack_states)
    cd=s.crit_damage_up+15*attack_states.get('heart',0)
    defense_up=s.defense_up+flower(defense_states)+(60 if defense_states.get('defense') else 0)
    a=replace(a,defense=a.defense*(1+(flower(attack_states)+(60 if attack_states.get('defense') else 0))/100))
    # Opposing attack is needed for attack-difference passives.
    d=replace(d,attack=d.attack*(1+(25*defense_states.get('heart',0)+flower(defense_states))/100))
    if defense_states.get('execution',0)*6 >= 100:
        raise ValueError('行刑式减伤达到或超过100%，结算上限待验证，暂不能计算')
    factor=s.damage_multiplier
    factor*=1+.08*attack_states.get('execution',0)
    factor*=1-.06*defense_states.get('execution',0)
    factor*=1-.1*defense_states.get('color',0)
    factor*=1+.06*defense_states.get('feather',0)
    if attack_states.get('weak'):factor*=.75
    if defense_states.get('paper'):factor*=.65
    factor*=1+.035*attack_states.get('dataflow',0)
    shared_bonus=s.card_sun_bonus
    if attack_states.get('sun'):shared_bonus+=s.sun_base_bonus+s.sun_per_buff_bonus*(attack_states['sun']-1)
    if defense_states.get('sun'):factor*=.8
    if s.critical and defense_states.get('scales'):factor*=.7
    for key,pct in [('guard',30),('threat',30),('jade',40)]:
        if defense_states.get(key):factor*=1-pct/100
    factor*=max(0,1-.18*defense_states.get('heart',0))
    if defense_states.get('vulnerable'):factor*=1.3
    if defense_states.get('nightmare'):factor*=1.15
    if attack_states.get('frost'):factor*=1.25
    if s.critical:factor*=1+.07*defense_states.get('lastwords',0)
    return replace(s,attacker=a,defender=d,attack_up=attack_up,crit_damage_up=cd,
                   defense_up=defense_up,damage_multiplier=factor,card_sun_bonus=shared_bonus,
                   final_multiplier=s.final_multiplier*(.75 if defense_states.get('tiamat') else 1),
                   sleeping=bool(defense_states.get('sleep')),first_hit_multiplier=s.first_hit_multiplier*(1.25 if defense_states.get('sleep') else 1))
