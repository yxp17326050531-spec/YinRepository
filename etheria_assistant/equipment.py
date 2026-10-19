"""Equipment projections and filters. Original network observations stay unchanged."""
ATTRIBUTES = {
    3:('生命加成',10,'%'), 4:('生命',100,''),
    7:('攻击加成',10,'%'), 8:('攻击',100,''),
    11:('防御加成',10,'%'), 12:('防御',100,''), 16:('速度',100,''),
    19:('暴击率',10,'%'), 22:('暴击伤害',10,'%'),
    25:('效果命中',10,'%'), 28:('效果抵抗',10,'%'),
}
RARITIES = ['传说','超凡','卓越','特异','稀有','精良','普通']
# Exact configuration IDs corroborated by the four supplied equipment screenshots.
# No rarity/slot rule is inferred from decimal digits of an unknown config ID.
KNOWN_LEGENDARY_CONFIGS = {15072,16131,17832,17752}
UNKNOWN = 'unknown'
FILTER_KEYS = ('matrix','points','rarity','initial','main','subs')


def normalize_sort(value):
    value = value if isinstance(value, dict) else {}
    keys = {'default','level',*[f'attr:{tag}' for tag in ATTRIBUTES]}
    return {'key':value.get('key') if value.get('key') in keys else 'default',
            'scope':value.get('scope') if value.get('scope') in ('subs','main','all') else 'subs',
            'descending':value.get('descending',True) is not False}


def gear_sort_value(gear, spec):
    spec = normalize_sort(spec)
    if spec['key'] == 'level':return gear.get('level')
    if not spec['key'].startswith('attr:'):return None
    tag = int(spec['key'].split(':')[1])
    attrs = project_gear(gear)['attributes']
    if spec['scope'] == 'subs':attrs = attrs[1:]
    elif spec['scope'] == 'main':attrs = attrs[:1]
    values = [a['value'] for a in attrs if a['type'] == tag and a['value'] is not None]
    return sum(values) if values else None


def sort_gear(gear, spec):
    spec = normalize_sort(spec)
    if spec['key'] == 'default':return list(gear)
    def key(g):
        value = gear_sort_value(g,spec)
        # Unknown/missing values stay last in either direction; equal values use UID.
        return (value is None, (-value if spec['descending'] else value) if value is not None else 0, g['uid'])
    return sorted(gear,key=key)


def decode_attribute(raw):
    tag = (raw >> 4) & 255
    spec = ATTRIBUTES.get(tag)
    return {'raw':raw, 'type':tag, 'name':spec[0] if spec else f'未知属性 #{tag}',
            'value':(raw >> 12)/spec[1] if spec else None,
            'unit':spec[2] if spec else '', 'upgrade_count_tentative':raw & 15}


def attribute_text(attr):
    return (f"{attr['name']} +{attr['value']:g}{attr['unit']}" if attr['value'] is not None
            else attr['name'] + '（保留原值）')


def project_gear(gear, metadata=None):
    metadata = metadata or {}
    attrs = [decode_attribute(v) for v in gear.get('attributes_raw', [])]
    rarity = metadata.get('rarity', '传说' if gear.get('config_id') in KNOWN_LEGENDARY_CONFIGS else UNKNOWN)
    initial = metadata.get('initial_sub_count', gear.get('initial_sub_count', UNKNOWN))
    return {'attributes':attrs, 'main':attrs[0] if attrs else None, 'subs':attrs[1:],
            'rarity':rarity, 'initial':UNKNOWN if initial is None else initial}


def normalize_filters(value):
    out = {}
    for key in FILTER_KEYS:
        values = value.get(key, []) if isinstance(value, dict) else []
        out[key] = sorted({str(v) for v in values}) if isinstance(values, (list,tuple,set)) else []
    return out


def matches_gear(gear, filters, metadata=None):
    filters = normalize_filters(filters)
    p = project_gear(gear, metadata)
    matrix = gear.get('matrix') or {}
    main = p['main']
    values = {'matrix':matrix.get('id'), 'points':matrix.get('points'),
              'rarity':p['rarity'], 'initial':p['initial'],
              'main':main['type'] if main and main['type'] in ATTRIBUTES else UNKNOWN}
    for key,value in values.items():
        value = UNKNOWN if value is None else str(value)
        if filters[key] and value not in filters[key]:
            return False
    # Within a subattribute group, ALL selections must occur on the same item.
    subtypes = {str(a['type']) if a['type'] in ATTRIBUTES else UNKNOWN for a in p['subs']}
    return set(filters['subs']).issubset(subtypes)


def filter_options(mappings, gear):
    ids = set(mappings.get('matrices', {}))
    ids.update(str(g['matrix']['id']) for g in gear if (g.get('matrix') or {}).get('id') is not None)
    matrices = [(key,mappings.get('matrices', {}).get(key,f'矩阵 #{key}')) for key in sorted(ids,key=int)]
    attrs = [(str(k),v[0]) for k,v in ATTRIBUTES.items()]
    return {'matrix':matrices+[(UNKNOWN,'未知')],
            'points':[(str(i),f'+{i}') for i in sorted({1,2,3} | {
                g['matrix']['points'] for g in gear if isinstance((g.get('matrix') or {}).get('points'),int)})]+[(UNKNOWN,'未知')],
            'rarity':[(v,v) for v in RARITIES]+[(UNKNOWN,'未知')],
            'initial':[(str(i),str(i)) for i in range(5)]+[(UNKNOWN,'未知')],
            'main':attrs+[(UNKNOWN,'未知')], 'subs':attrs+[(UNKNOWN,'未知属性')]}


def filter_summary(filters, options):
    titles = {'matrix':'矩阵','points':'矩阵点数','rarity':'稀有度','initial':'初始副属性条数','main':'主属性','subs':'副属性全部包含'}
    parts = []
    for key,selected in normalize_filters(filters).items():
        if selected:
            labels = dict(options[key])
            parts.append(titles[key]+'：'+(' + ' if key=='subs' else ' / ').join(labels.get(v,v) for v in selected))
    return '；'.join(parts) or '全部源器 · 尚未设置筛选'
