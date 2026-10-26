"""Deterministic, offline damage estimates. These are explicit models, not protocol facts.

Percent inputs use panel units (12 means 12%). No archive writes or equipment
inventory lookups. See DAMAGE_CALCULATOR.md for formulas and unresolved mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from battle_attributes import decode_extra_attributes

MODELS = {'template': '模板主公式', 'kzone': 'Kzone备选（含条件900下限）'}
EFFECT_POINTS = {'收割': 8, '狂怒': 8, '沸腾打击': 12, '浴血之躯': 12, '涌泉': 12, '不屈之誓': 12, '洞悉穿刺': 12, '乘势追击': 12, '亵渎': 8}
EXTRA_KEYS = ('pvp_damage_bonus', 'pvp_damage_reduction', 'extra_damage_reduction',
              'ignore_defense', 'damage_result_bonus', 'damage_result_reduction')


def _confirmed(row):
    return row.get('confidence') in ('已对照样本', '用户映射')


def import_unit(unit):
    """Snapshot projected roster values; absence stays None, manual loadout wins."""
    stats = unit.get('stats') or {}
    percents = unit.get('percent_attributes_tentative') or {}
    extras = decode_extra_attributes(unit.get('attributes_raw'))
    values = {k: stats.get(k) for k in ('attack', 'defense', 'hp')}
    values.update({k: percents.get(k) for k in ('crit', 'crit_damage')})
    values.update({k: extras.get(k) for k in EXTRA_KEYS})
    manual = unit.get('manual') or {}
    override = manual.get('matrices')
    matrices = override if override is not None else unit.get('matrix_effects_candidates', [])
    active = set()
    labels = []
    for row in matrices:
        name = row.get('name', '?')
        points = row.get('points') if override is not None else row.get('threshold')
        confirmed = override is not None or _confirmed(row)
        labels.append(f'{name} {points if points is not None else "?"}点' +
                      (' [手动]' if override is not None else '' if confirmed else ' [候选]'))
        if name in EFFECT_POINTS and isinstance(points, (int, float)) and points >= EFFECT_POINTS[name] and confirmed:
            active.add(name)
    shell_rows = unit.get('shells') or []
    shell_names = list(dict.fromkeys(row.get('name', '?') for row in shell_rows))
    if manual.get('shell') is not None:
        shell_names = [manual['shell']] if manual['shell'] else []
        shell = shell_names[0] if shell_names and shell_names[0] in ('启示录', '伯爵','噬身之蛇','宝剑七','白獠武者','寅虎') else '无 / 手动'
    else:
        known = {r['name'] for r in shell_rows if _confirmed(r)}
        shell = next(iter(known)) if len(known) == 1 and len(shell_names) == 1 and known <= {'启示录', '伯爵','噬身之蛇','宝剑七','白獠武者','寅虎'} else '无 / 手动'
    return {'name': unit.get('hero_name', f"角色 #{unit.get('hero_id', '?')}"),
            'values': values, 'active_effects': active, 'matrices': list(dict.fromkeys(labels)),
            'shell_names': shell_names, 'shell': shell,
            'unapplied_extras': {k: v for k, v in extras.items() if k not in EXTRA_KEYS}}


@dataclass
class Fighter:
    attack: float = 0
    defense: float = 0
    hp: float = 1
    crit_damage: float = 100
    pvp_damage_bonus: float = 0
    pvp_damage_reduction: float = 0
    extra_damage_reduction: float = 0
    ignore_defense: float = 0
    damage_result_bonus: float = 0
    damage_result_reduction: float = 0


@dataclass
class Scenario:
    attacker: Fighter = field(default_factory=Fighter)
    defender: Fighter = field(default_factory=Fighter)
    spring: bool = False
    unyielding: bool = False
    insight: bool = False
    prior_damage_events: int = 0
    opportunist: int = 0
    shield_bonus: bool = False
    shield_hp: float = 0
    seven_control: bool = False
    sleeping: bool = False
    model: str = 'template'
    scaling: str = 'attack'
    ratios: tuple[float, ...] = (1.0,)
    critical: bool = True
    pvp: bool = True
    attack_up: float = 0
    attack_down: float = 0
    crit_damage_up: float = 0
    defense_up: float = 0
    defense_down: float = 0
    flat_defense_down: float = 0
    other_ignore: float = 0
    damage_multiplier: float = 1
    target_multiplier: float = 1
    first_hit_multiplier: float = 1
    final_multiplier: float = 1
    harvest: bool = False
    fury: bool = False
    boiling: bool = False
    bloodbath: bool = False
    bloodbath_spent: float = 0
    remaining_hp: float | None = None
    shell: str = '无 / 手动'
    count_attack_percent: float = 0   # old workbook=0; user's newer description=10
    quilo_passive: bool = False


def defense_terms(base, multiplier, flat_down, model):
    """Return effective DEF and damage divisor, faithfully separating workbook models."""
    effective = base * multiplier - flat_down
    if model == 'template':
        effective = max(0.0, effective)
        return effective, effective / 1000 + 1.05
    if model != 'kzone':
        raise ValueError('未知防御模型')
    floor = 900 if multiplier < 1 and base > 400 else 400
    effective = max(effective, floor)
    compressed = (effective - 1500) / 2 + 1500 if effective > 1500 else effective
    return effective, .7 * compressed / 400


def _validate(s):
    if s.model not in MODELS or s.scaling not in ('attack', 'defense', 'hp'):
        raise ValueError('请选择支持的防御模型和技能缩放属性')
    if s.shell not in ('无 / 手动', '启示录', '伯爵', '宝剑七', '噬身之蛇'):
        raise ValueError('该智壳尚未建模，请选无 / 手动并自行设置乘区')
    for f in (s.attacker, s.defender):
        if any(not isinstance(v, (int, float)) or not isfinite(v) for v in vars(f).values()):
            raise ValueError('面板必须是有限数字')
        if f.hp <= 0 or min(f.attack, f.defense, f.crit_damage) < 0:
            raise ValueError('生命须大于0；攻击、防御、暴击伤害不能为负')
        for k in ('pvp_damage_reduction', 'extra_damage_reduction', 'damage_result_reduction', 'ignore_defense'):
            if not 0 <= getattr(f, k) <= 100:
                raise ValueError(f'{k} 超出本模型支持的0–100%，请核实原值')
        if f.pvp_damage_bonus < 0 or f.damage_result_bonus < 0:
            raise ValueError('增伤不能为负')
    if not s.ratios or len(s.ratios) > 20 or any(not isfinite(x) or x < 0 for x in s.ratios):
        raise ValueError('技能需包含1–20段非负、有限倍率')
    for key in ('attack_up', 'attack_down', 'crit_damage_up', 'defense_up', 'defense_down',
                'flat_defense_down', 'other_ignore', 'damage_multiplier', 'target_multiplier',
                'bloodbath_spent', 'count_attack_percent', 'first_hit_multiplier', 'shield_hp', 'final_multiplier'):
        v = getattr(s, key)
        if not isinstance(v, (int, float)) or not isfinite(v) or v < 0:
            raise ValueError('增减益及乘区必须是非负有限数字')
    if max(s.attack_down, s.defense_down, s.other_ignore) > 100:
        raise ValueError('减攻、减防、额外无视防御须在0–100%之间')
    if not 0 <= s.opportunist <= 6 or not isinstance(s.opportunist,int) or not isinstance(s.prior_damage_events,int) or not 0 <= s.prior_damage_events <= 3:
        raise ValueError('乘势追击种类须0–6，回合既有伤害次数须0–3')
    if s.shield_hp and s.bloodbath:
        raise ValueError('护盾与浴血的结算先后待验证，暂不同时计算')
    if s.remaining_hp is not None and (not isfinite(s.remaining_hp) or not 0 < s.remaining_hp <= s.defender.hp):
        raise ValueError('当前生命须大于0且不超过最大生命')


def calculate(s):
    """Per-hit threshold simulation. Stop on death; overkill never generates a shell proc."""
    _validate(s)
    a, d = s.attacker, s.defender
    count_bonus = 1200 + a.attack * s.count_attack_percent / 100 if s.shell == '伯爵' else 0
    attack = max(0.0, a.attack * (1 + (s.attack_up - s.attack_down) / 100) + count_bonus)
    scaling = {'attack': attack, 'defense': a.defense, 'hp': a.hp}[s.scaling]
    critical = (a.crit_damage + s.crit_damage_up) / 100 if s.critical else 1
    passive = 1 + min(.9, max(0.0, attack - d.attack) * .0003) if s.quilo_passive else 1
    pvp = .7 * (1 + a.pvp_damage_bonus / 100) * (1 - d.pvp_damage_reduction / 100) if s.pvp else 1
    factor = (critical * passive * pvp * (1 - d.extra_damage_reduction / 100) *
              (1 + (a.damage_result_bonus + (12 if s.fury and s.critical else 0)) / 100) *
              (1 - d.damage_result_reduction / 100) * s.damage_multiplier * s.target_multiplier)
    hp = d.hp if s.remaining_hp is None else s.remaining_hp
    start_hp, spent, rows = hp, s.bloodbath_spent, []
    shield = s.shield_hp
    damage_events = s.prior_damage_events

    def apply_damage(raw):
        nonlocal hp, spent, shield
        # Bloodbath: damage up to 20% max HP is full, excess takes 45%.
        if s.bloodbath:
            available = max(0.0, d.hp * .2 - spent)
            mitigated = min(raw, available) + max(0.0, raw - available) * .45
        else:
            mitigated = raw
        mitigated *= s.final_multiplier
        absorbed = min(shield, mitigated)
        shield -= absorbed
        actual = min(hp, mitigated - absorbed)
        hp = max(0.0, hp - actual)
        spent += actual
        return mitigated, actual

    for i, ratio in enumerate(s.ratios):
        before = hp
        harvest = s.harvest and hp > d.hp * .5
        mult = ((1 + (s.defense_up - s.defense_down) / 100) *
                (1 - a.ignore_defense / 100) * (1 - s.other_ignore / 100) * (.6 if harvest else 1))
        effective, divisor = defense_terms(d.defense, mult, s.flat_defense_down, s.model)
        boil = min(1.8, 1 + .4 * i) if s.boiling else 1
        conditional = (.75 if s.spring else 1) * ((.6 if hp < d.hp*.55 else .8) if s.unyielding else 1)
        conditional *= 1 + .06*s.opportunist
        conditional *= 1.4 if s.shield_bonus and shield > 0 else 1
        conditional *= (1.25,1.15,1.05)[damage_events] if s.insight and damage_events < 3 else 1
        conditional *= 1.5 if s.seven_control or (s.shell == '宝剑七' and s.sleeping and i == 0) else 1
        direct, direct_actual = apply_damage(scaling * ratio * factor * conditional * boil * (s.first_hit_multiplier if i == 0 else 1) / divisor)
        damage_events += 1
        shell = shell_actual = 0.0
        if hp > 0 and s.shell == '启示录' and s.critical:
            # Optional study assumption: true damage only takes PvP global 0.7 + Bloodbath.
            shell, shell_actual = apply_damage(min(d.hp * .12, attack * 1.8) * (.7 if s.pvp else 1))
            damage_events += 1
        rows.append({'hit': i + 1, 'before': before, 'effective_defense': effective,
                     'divisor': divisor, 'harvest': harvest, 'boiling': boil,
                     'direct': direct, 'shell': shell, 'actual': direct_actual + shell_actual,
                     'remaining': hp, 'shield_remaining': shield, 'killed_by': ('技能' if direct_actual >= before else '启示录') if hp == 0 else None})
        if hp == 0:
            break
    return {'rows': rows, 'damage': start_hp - hp, 'remaining': hp, 'killed': hp == 0,
            'kill_hit': rows[-1]['hit'] if hp == 0 else None, 'combat_attack': attack,
            'passive_multiplier': passive, 'model': s.model}
