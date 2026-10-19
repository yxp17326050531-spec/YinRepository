"""Roster totals verified by wear/remove/restore comparisons.

Battle tags differ from component IDs. Only the explicitly verified tags use
the observed bit-63 marker/magnitude encoding; unknown values stay untouched.
"""
from collections import Counter

BASE_TAGS = frozenset((1, 5, 9, 13, 17, 20, 23, 26))
EXTRA_ATTRIBUTES = {
    171: ('pvp_damage_bonus', 'PVP增伤'),
    174: ('pvp_damage_reduction', 'PVP减伤'),
    41: ('extra_damage_reduction', '额外减伤'),
    58: ('ignore_defense', '无视防御'),
    80: ('damage_result_bonus', '伤害结果增伤'),
    83: ('damage_result_reduction', '伤害结果减伤'),
    179: ('boss_damage_bonus', '首领增伤'),
    180: ('crit_damage_bonus', '暴击增伤'),
    183: ('crit_damage_reduction', '被暴击减伤'),
    191: ('ultimate_damage_reduction', '终极技能减伤'),
    194: ('basic_damage_bonus', '普攻增伤'),
    91: ('shield_bonus', '护盾量'),
}
MAGNITUDE_MASK = (1 << 63) - 1


def decode_extra_attributes(raw):
    """Use transmitted totals once. Duplicate known tags are ambiguous, not additive."""
    if raw is None:
        return {}
    counts = Counter(value & 255 for value in raw)
    return {EXTRA_ATTRIBUTES[value & 255][0]: ((value & MAGNITUDE_MASK) >> 8) / 10
            for value in raw if (value & 255) in EXTRA_ATTRIBUTES and counts[value & 255] == 1}


def pending_attributes(unit):
    raw = unit.get('attributes_raw')
    if raw is None:
        return None
    counts = Counter(value & 255 for value in raw)
    return [{'tag': value & 255, 'raw': value, 'upper_raw': value >> 8}
            for value in raw if (value & 255) not in BASE_TAGS and
            ((value & 255) not in EXTRA_ATTRIBUTES or counts[value & 255] != 1)]


def extra_text(unit):
    values = decode_extra_attributes(unit.get('attributes_raw'))
    lines = ['对局开场已下发属性（同一字段直接显示，不再次叠加库存）：']
    lines.extend(f'{name}：{values[key]:g}%' if key in values else f'{name}：—'
                 for key, name in EXTRA_ATTRIBUTES.values())
    lines.extend(['PVP字段已对照科技与元件的合计；其他字段不保证含全部矩阵或技能效果。',
                  '潜能提供的额外减伤与涌泉矩阵效果分开记录，不将数值互相替换。',
                  '普通与相性增伤按用户确认归同一增伤区间；条件值未下发时不补入。',
                  '额外减伤与伤害结果减伤分别显示，不相加为最终减伤率。',
                  '这是阵容消息下发的开场数值；不推算条件技能触发后的伤害。'])
    return '\n'.join(lines)


def pending_text(unit):
    rows = pending_attributes(unit)
    intro = '其他属性待对照；已确认增减伤在上方单独显示。'
    if rows is None:
        return intro + '\n此旧记录未保存属性整数，需重新导入抓包或采集一场新对局。'
    if not rows:
        return intro + '\n本次阵容没有其他待对照属性；缺失不代表0。'
    lines = [intro, f'保留 {len(rows)} 项待对照属性。编号与元件编号独立，载荷不是已确认百分比。']
    lines.extend(f"#{r['tag']} · 原值 {r['raw']} · 高8位以上载荷 {r['upper_raw']}" for r in rows)
    return '\n'.join(lines)
