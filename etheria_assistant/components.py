"""Screenshot-verified component projections, separate from gear encoding.

Never mutate login records. Bits 8..15 are retained without assigning meaning.
Exclusive bonuses depend on a matching observed group, not merely ownership.
"""
from decimal import Decimal, ROUND_HALF_UP


def decode_attribute(raw, mappings):
    identifier = raw & 255
    definition = mappings.get('component_attributes', {}).get(str(identifier))
    out = {'raw': raw, 'id': identifier, 'metadata_raw': (raw >> 8) & 255,
           'amount_raw': raw >> 16, 'name': f'属性 #{identifier}（待确认）',
           'value': None, 'unit': '', 'digits': None}
    if definition:
        out.update(name=definition['name'], unit=definition['unit'], digits=definition['digits'],
                   value=float(Decimal(raw >> 16) / Decimal(definition['divisor'])))
    return out


def attribute_text(attribute, multiplier=1):
    if attribute['value'] is None:
        return f"{attribute['name']} · 原值 {attribute['raw']}"
    value = Decimal(str(attribute['value'])) * Decimal(str(multiplier))
    value = value.quantize(Decimal(1).scaleb(-attribute['digits']), rounding=ROUND_HALF_UP)
    return f"{attribute['name']} +{value}{attribute['unit']}"


def imprint_name(identifier, mappings):
    return mappings.get('component_imprints', {}).get(str(identifier), f'刻影类型 #{identifier}（待确认）')


def project_component(item, groups, mappings):
    config = item.get('config_id_raw')
    definition = mappings.get('component_configs', {}).get(str(config), {})
    exclusive = item.get('field3_raw')
    holders = []
    for group in groups:
        for slot, uid in enumerate(group.get('component_uids_raw', []), 1):
            if uid != item['uid']:
                continue
            identifier = group['id_raw']
            # Only screenshot-confirmed exclusive types receive the observed 20% rule.
            bonus = mappings.get('component_exclusive_bonus', {}).get(str(exclusive))
            active = exclusive == identifier and bonus is not None
            holders.append({'id': identifier, 'name': imprint_name(identifier, mappings),
                            'slot': slot, 'bonus_active': active, 'multiplier': 1 + bonus / 100 if active else 1})
    flag = item.get('field6_raw')
    return {'uid': item['uid'], 'name': definition.get('name', f'元件配置 #{config}（待确认）'),
            'rarity': definition.get('rarity', '待确认'),
            'attributes': [decode_attribute(raw, mappings) for raw in item.get('attributes_raw', [])],
            'exclusive': imprint_name(exclusive, mappings) if exclusive is not None else '未见专属标志',
            'lock': '已锁定（样本对照）' if flag == 1 else '未见锁定标志' if flag is None else f'标志 {flag}（待确认）',
            'holders': holders}


def component_detail(item, projection):
    import json
    lines = [f"{projection['name']} · {projection['rarity']} · #{item['uid']}",
             f"专属：{projection['exclusive']} · {projection['lock']}", '基础属性：']
    lines.extend('  ' + attribute_text(a) for a in projection['attributes'])
    if not projection['holders']:
        lines.append('装配：无已观测引用；以上为基础值。')
    for holder in projection['holders']:
        lines.append(f"装配：{holder['name']} · 槽{holder['slot']}" +
                     (' · 专属加成20%已计入以下值' if holder['bonus_active'] else ' · 未计入专属加成'))
        lines.extend('  ' + attribute_text(a, holder['multiplier']) for a in projection['attributes'])
    lines.extend(['仅登录快照；未知属性及标志保留原值。', '原始记录：',
                  json.dumps(item, ensure_ascii=False, indent=2)])
    return '\n'.join(lines)
