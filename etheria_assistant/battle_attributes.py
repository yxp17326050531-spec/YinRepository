"""Uninterpreted roster attributes for controlled equipment comparisons.

These tags are a different namespace from component attribute IDs. High bits
are not assumed to be a sign, tier, or percent representation.
"""
KNOWN_TAGS = frozenset((1, 5, 9, 13, 17, 20, 23, 26))


def pending_attributes(unit):
    raw = unit.get('attributes_raw')
    if raw is None:
        return None
    return [{'tag': value & 255, 'raw': value, 'upper_raw': value >> 8}
            for value in raw if (value & 255) not in KNOWN_TAGS]


def pending_text(unit):
    rows = pending_attributes(unit)
    intro = '增伤 / 减伤 / 无视防御：对局字段对应关系待确认。'
    if rows is None:
        return intro + '\n此旧记录未保存属性整数，需重新导入抓包或采集一场新对局。'
    if not rows:
        return intro + '\n本次阵容没有下发八项已知属性以外的属性整数；缺失不代表0。'
    lines = [intro, f'保留 {len(rows)} 项待对照属性。编号与元件编号独立，载荷不是已确认百分比。']
    lines.extend(f"#{r['tag']} · 原值 {r['raw']} · 高8位以上载荷 {r['upper_raw']}" for r in rows)
    return '\n'.join(lines)
