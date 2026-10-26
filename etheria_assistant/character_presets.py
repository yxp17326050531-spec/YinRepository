"""Independent screenshot-based character skill presets. No hero-ID guesses."""
from dataclasses import replace

# Each character owns its skills and parameter rules; generic edits aren't saved here.
CHARACTERS = {
 '魁洛': {'skills': {'quilo_s3': {'name':'三段大招（研究模板）','ratios':(1.1,1.1,1.1),'scaling':'attack','aoe':True}},
         'note':'原研究模板：主目标×1.75，残心攻差上限90%；未加入照破。'},
 '博尔涅': {'skills': {'borne_s3': {'name':'天狼吠月·Lv5','ratios':(6.0,),'scaling':'attack','aoe':True}},
         'note':'牧夜行Lv5：入场生命增加入场攻击×800%；每次攻击附加自身最大生命60%，无法暴击。天狼吠月以超过4个存活敌人时600%为基础，每少1人追加一段250%。60%生命附伤的攻击/分段口径与乘区待验证，须手选。'},
 '弥瑟亚': {'skills': {
     'misaya_s1': {'name':'反逆十字·Lv4','ratios':(1.3,1.3),'scaling':'attack','aoe':False},
     'misaya_s3': {'name':'降神·Lv5','ratios':(2.0,2.0),'scaling':'attack','aoe':True}},
     'note':'审判：攻击无视目标70%防御。降神两段200%，额外无视目标被动；反逆十字25%易伤不自动判定命中。击杀后的无敌/免疫不影响本次输出。'},
 '千羽': {'skills': {'qianyu_s3': {'name':'明光裁定·Lv5','ratios':(.8,.8,.8,.8),'scaling':'attack','aoe':True}},
         'note':'先为己方附加速度上升30%，再造成4段80%。每高于目标1点速度，伤害额外+0.6%；是否存在隐藏上限待验证。30%驱散按概率，不自动改目标增益。'},
}
PASSIVE_STATES = frozenset({'tiamat','scales','color','execution','heart'})


def apply_character(s, skill, *, alive=0, hp_mode=0, entry_attack=0, hp_damage_mode=0,
                    attacker_speed=None, defender_speed=None, speed_up=False, defender_speed_up=False,
                    attacker_speed_down=False, defender_speed_down=False, passive_checked=False,
                    defense_states=None, attacker_states=None, legacy_flower=0):
    """Apply only selected character parameters. Missing evidence must be explicit."""
    if skill is None:return s
    states = defense_states or {}; own = attacker_states or {}
    if skill == 'quilo_s3':return replace(s,quilo_passive=True)
    if skill == 'borne_s3':
        if not 1 <= alive <= 12:raise ValueError('博尔涅：请填写当前存活敌人数1–12，不从开场人数猜存活')
        if hp_mode not in (1,2):raise ValueError('博尔涅：请确认导入生命是否已包含牧夜行入场加成')
        if hp_mode == 2 and entry_attack <= 0:raise ValueError('博尔涅：请填写入场攻击，不能使用临时攻击buff推算')
        if hp_damage_mode not in (1,2):raise ValueError('博尔涅：请选择60%生命附伤按每段或仅首段试算；口径待验证')
        if not passive_checked:raise ValueError('天狼吠月：请确认已手动排除目标被动')
        if PASSIVE_STATES & states.keys():raise ValueError('天狼吠月：请清除目标角色被动状态（保留装备矩阵）')
        a=replace(s.attacker,hp=s.attacker.hp+(8*entry_attack if hp_mode==2 else 0))
        extra=a.hp*.6
        # Explicit study assumption: attached HP damage shares the skill's damage divisor.
        return replace(s,attacker=a,critical=False,ratios=(6.0,)+(2.5,)*max(0,5-alive),
                       extra_hit_damage=extra,extra_first_only=hp_damage_mode==2,
                       followup_ratios=(1.1,1.1) if s.shell=='白獠武者' else (),
                       followup_flat_damage=extra if s.shell=='白獠武者' else 0)
    if skill in ('misaya_s1','misaya_s3'):
        if s.other_ignore:raise ValueError('弥瑟亚：70%无视已由角色预设提供，请勿在额外无视栏重复填写')
        if skill=='misaya_s3':
            if not passive_checked:raise ValueError('降神：请确认已手动排除目标被动；不自动猜矩阵、增益是否属于被动')
            if PASSIVE_STATES & states.keys():raise ValueError('降神：请清除目标角色被动状态后再计算（保留装备矩阵）')
        return replace(s,other_ignore=70)
    if skill=='qianyu_s3':
        if attacker_speed is None or defender_speed is None:raise ValueError('千羽：请填写双方速度，缺失不是0')
        # Cast applies speed-up before damage; don't stack it again with an existing identical buff.
        def speed(base,status,up,down,casting=False):
            flower=status.get('flower',0); flower=30 if flower==3 else flower*6
            pct=flower+(30 if up or casting else 0)-(30 if down else 0)
            return max(0,base*(1+pct/100)+3*status.get('dataflow',0)-3*status.get('feather',0))
        av=speed(attacker_speed,own,speed_up,attacker_speed_down,True)
        if not own.get('flower'):av+=attacker_speed*legacy_flower/100
        dv=speed(defender_speed,states,defender_speed_up,defender_speed_down)
        return replace(s,damage_multiplier=s.damage_multiplier*(1+max(0,av-dv)*.006))
    raise ValueError('未知角色技能预设')
