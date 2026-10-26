"""Plain-text audit rendered from the same scenario and traces used for calculation."""
from damage_calculator import MODELS


def formula_text(s,r):
    a,d=s.attacker,s.defender
    f=lambda value: f'{value:,.8f}'.rstrip('0').rstrip('.') if isinstance(value,(int,float)) else str(value)
    lines=[
        '当前实现模型（研究假设，不代表已验证的全部游戏规则）',
        '实际生效智壳：'+r['active_shell'],
        '模型：'+MODELS[s.model],
        '', '一、战斗攻击',
        '战斗攻击 = max(0, 面板攻击 × [1 + (攻击增加% − 攻击降低%)/100] + 伯爵固定攻击)',
        f"= max(0, {f(a.attack)} × [1 + ({f(s.attack_up)} − {f(s.attack_down)})/100] + {f(r['count_bonus'])}) = {f(r['combat_attack'])}"]
    if s.shell=='伯爵':
        lines.append(f"伯爵固定攻击 = 1200 + 白字攻击 {f(s.count_base_attack if s.count_attack_percent else 0)} × {f(s.count_attack_percent)}% = {f(r['count_bonus'])}；在攻击百分比增益之后加上")
    else:lines.append('未启用伯爵，伯爵固定攻击 = 0；切换智壳不会保留该加成。')
    lines += ['', '二、共用乘区',
        f'暴击倍率 = ({f(a.crit_damage)} + {f(s.crit_damage_up)})/100（非暴击时为1）',
        f'残心 = 1 + min(0.9, max(0, 战斗攻击 − 守方攻击 {f(d.attack)}) × 0.0003)（未启用时为1）',
        f'PVP乘区 = 0.7 × (1 + {f(a.pvp_damage_bonus)}/100) × (1 − {f(d.pvp_damage_reduction)}/100)（非PVP时为1）',
        f'结果增伤区 = 1 + (面板 {f(a.damage_result_bonus)} + 手填 {f(s.manual_attribute_bonus)})/100',
        f'魔术牌/日轮同区 = 1 + {f(s.card_sun_bonus)}/100',
        f'屠夫仅攻方当前生命>90%触发；当前生命%={s.attacker_hp_percent}，档位={f(s.butcher_bonus)}%',
        '下列共用系数逐项相乘（1表示本次没有修正）：']
    lines.extend(f'  {name} ×{f(value)}' for name,value in r['factor_components'])
    lines.append('共用系数 F = '+ ' × '.join(f(value) for _,value in r['factor_components'])+' = '+f(r['factor']))
    lines += ['', '三、防御模型',
        f'基础防御 {f(d.defense)}；防御增加 {f(s.defense_up)}%；防御降低 {f(s.defense_down)}%；面板穿防 {f(a.ignore_defense)}%；额外穿防 {f(s.other_ignore)}%；固定减防 {f(s.flat_defense_down)}',
        'm = [1 + (防御增加% − 防御降低%)/100] × (1 − 面板穿防%/100) × (1 − 额外穿防%/100) × 收割系数',
        '收割系数：启用且段前生命严格高于最大生命50%时0.6，否则1。']
    if s.model=='template':lines += ['有效防御 = max(0, 基础防御 × m − 固定减防)', '防御除数 = 有效防御/1000 + 1.05']
    else:lines += ['下限 = 900（m<1且基础防御>400），其他情况400', '有效防御 = max(基础防御 × m − 固定减防, 下限)', '压缩防御 = (有效防御−1500)/2+1500（有效防御>1500），否则保持原值', '防御除数 = 0.7 × 压缩防御/400；这是Kzone备选，不与主公式混用。']
    lines += ['', '四、逐段计算',
        '原伤 R = 基础伤害 B × 损血增伤 × F × 技能类型系数 × 主目标乘数 × 条件系数 × 沸腾 × 首段系数 ÷ 防御除数',
        'B = 缩放属性 × 本段倍率 + 附伤；白獠追击改用战斗攻击×追击倍率+追击附伤。',
        '弥瑟亚二技能仅末段附伤 = min(段前已损失生命, 战斗攻击×3.5)，暂按技能共用乘区。',
        '魁洛二技能损血增伤 = 1 + 段前已损失生命/最大生命。',
        f'本次技能类型={s.skill_kind}；终极技能仅使用守方终极减伤 {f(d.ultimate_damage_reduction)}%；普攻仅使用攻方普攻增伤 {f(a.basic_damage_bonus)}%；其他技能类型系数为1。',
        '条件系数合并涌泉、不屈、乘势、亵渎、洞悉、宝剑七；状态与其他独立乘区合计已包含所选角色状态。',
        f'洞悉此前伤害次数={s.prior_damage_events}，每段计次={s.insight_events_per_hit}；默认逐段1次。',
        '护盾先吸收且不累计浴血；本次盾吸收 S=min(剩余护盾,R×最终系数)。',
        '溢出原伤 H=max(0,R−S/最终系数)；最终系数为0时H=0。此换算保留无盾时的浴血/分摊模型。',
        f'浴血：余量 A=max(0, 最大生命 {f(d.hp)}×20% − 本回合累计实际扣血)。仅溢出部分H参与：M=min(H,A)+max(0,H−A)×0.45；未启用时M=H。',
        f'分摊等最终系数={f(s.final_multiplier)}；生命伤害=M×最终系数；实际扣血封顶到当前生命；结算伤害（含盾吸收）=S+生命伤害。',
        '以下数值来自本次计算实际执行的记录，生命附伤与状态使用角色处理后的面板。']
    for row in r['rows']:
        lines += ['',f"【{row['phase']}{row['phase_hit']}】段前生命 {f(row['before'])} / {f(d.hp)}；有效防御 {f(row['effective_defense'])}；收割 {'触发' if row['harvest'] else '不触发'}",
            '条件系数：'+' × '.join(name+' '+f(v) for name,v in row['conditional_components']),
            f"B={f(row['base_damage'])}（倍率 {f(row['ratio'])}；末段损血附伤原值 {f(row['finisher_base'])}）",
            f"R = {f(row['base_damage'])} × {f(row['lost_hp_multiplier'])} × {f(row['factor'])} × {f(row['typed_multiplier'])} × {f(row['target_multiplier'])} × {f(row['conditional_multiplier'])} × {f(row['boiling'])} × {f(row['first_multiplier'])} ÷ {f(row['divisor'])} = {f(row['direct_trace']['raw'])}"]
        for title,trace in [('技能/追击',row['direct_trace']),('启示录',row['shell_trace'])]:
            if trace is None:continue
            if title=='启示录':lines.append(f'启示录研究模型：min(最大生命×12%, 战斗攻击×1.8) × PVP全局系数={f(trace["raw"])}；不套普通直伤共用F。')
            lines.append(f"{title}：先盾吸收 {f(trace['absorbed'])}；溢出原伤 {f(trace['raw_for_hp'])}；浴血余量={f(trace['bloodbath_available']) if trace['bloodbath_available'] is not None else '本次不参与'}；浴血后 {f(trace['after_bloodbath'])} × 最终系数 {f(trace['final_multiplier'])}；实际扣血 {f(trace['actual'])}")
        lines.append(f"本段结算直伤 {f(row['direct'])}；智壳 {f(row['shell'])}；剩余生命 {f(row['remaining'])}")
    lines += ['', '死亡即停止后续段；实际扣血会封顶。同样击杀时，实际扣血可能不变，应同时比较结算伤害（含溢出）和击杀段数。',
        '公式可选中复制；调整参数后重新计算。此处展示实现模型，不能据此承诺所有实测误差均在±5%。']
    return '\n'.join(lines)
