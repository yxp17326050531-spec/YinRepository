"""Evidence-based mode and player perspective; protocol sides stay immutable."""
import hashlib
import json

KINDS = ['未分类', 'BP排位', '竞技场', 'GVG', 'PVE', '回放/观战', '练习/测试']


def mode_key(candidate):
    return f"{candidate['opcode']}:{candidate['path']}:{candidate['value']}"


def mode_info(battle, mappings=None):
    if battle.get('capture_context') == 'replay' or battle.get('source_opcode') == '0x8421':
        return {'kind': '回放/观战', 'origin': 'protocol', 'reason': '0x8421回放响应或明确选择的回放场景'}
    sizes=tuple(len(battle.get('teams',{}).get(t,[])) for t in ('A','B'))
    if all(sizes) and sizes==(3,3):
        return {'kind':'GVG','origin':'roster_size','reason':'按用户设定：双方各3名角色'}
    if all(sizes) and sizes!=(4,4):
        return {'kind':'PVE','origin':'roster_size','reason':'按用户设定：非4v4、非3v3'}
    known = (mappings or {}).get('battle_modes', {})
    hits = {known[mode_key(c)] for c in battle.get('mode_candidates', []) if mode_key(c) in known}
    hits &= set(KINDS) - {'未分类', '回放/观战'}
    if len(hits) == 1:
        return {'kind': hits.pop(), 'origin': 'user_mapping', 'reason': '开场字段命中用户确认的模式映射'}
    draft=battle.get('draft_evidence',{})
    legacy=(battle.get('participant_status')=='玩家方向已由确认选人和上场阵容交叉对应'
            and len(battle.get('participants',[]))==2
            and {p.get('team') for p in battle['participants']}=={'A','B'})
    if not hits and sizes==(4,4) and battle.get('source_opcode')=='0x6003' and (
            draft.get('confirmed_teams')==['A','B'] or legacy):
        return {'kind':'BP排位','origin':'confirmed_draft','reason':'4v4且本连接近期确认选人与双方上场阵容唯一对应'}
    return {'kind': '未分类', 'origin': 'unknown', 'reason': '模式映射冲突' if hits else '没有已确认的模式编号；BP消息仅作线索'}


def result_text(context):
    winner = context.get('winner', 'unknown')
    def victor(side):
        name = context.get('team_names', {}).get(side)
        return f'{side} 方获胜（{name}）' if name else f'{side} 方获胜'
    if context.get('sample_kind') == '回放/观战':
        protocol = context.get('protocol_winner')
        if protocol in ('A', 'B'):
            return victor(protocol) + ' · 观战，不计本人战绩'
        if protocol == 'draw':
            return '平局 · 观战，不计本人战绩'
        code=context.get('result_code')
        return (f'观战 · 结算 {code} · 胜方待确认 · 不计战绩' if code is not None else '回放 · 结果未确认 · 不计战绩')
    if winner == 'draw':
        return '平局'
    if winner not in ('A', 'B'):
        code=context.get('result_code')
        return f'结算 {code} · 胜方待确认' if code is not None else '结果未确认'
    own = context.get('own_team')
    if own not in ('A', 'B'):
        return victor(winner) + ' · 己方待确认'
    return '胜利' if winner == own else '失败'


def unit_fingerprint(unit):
    # Exact observed attributes and effects, never a hero ID alone.
    content = [unit['hero_id'], unit['stats'], unit.get('attributes_raw'),
               unit.get('percent_attributes_tentative'), sorted(unit['effects_raw'])]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def fingerprints(battle):
    return battle.get('_fingerprints') or {t:[unit_fingerprint(u) for u in units] for t,units in battle['teams'].items()}


def infer_side(battle, references):
    """Only unique, multi-unit matches against explicitly confirmed local teams."""
    hits = set()
    evidence = []
    current = {t:set(values) for t,values in fingerprints(battle).items()}
    for reference, own in references:
        if reference.get('capture_context') == 'replay':
            continue
        a, b = battle.get('capture_time'), reference.get('capture_time')
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or abs(a-b) > 86400:
            continue
        reference_prints = set(fingerprints(reference)[own])
        matched = {t: len(reference_prints & values) for t, values in current.items()}
        for team, count in matched.items():
            other = 'B' if team == 'A' else 'A'
            if count >= max(2, (len(current[team])+1)//2) and matched.get(other, 0) == 0:
                hits.add(team)
                evidence.append(count)
    if len(hits) == 1:
        return {'own_team': hits.pop(), 'side_origin': 'fingerprint',
                'side_reason': f'与24小时内手动确认的己方有至少{min(evidence)}个角色完整属性及效果一致（推定，可校正）'}
    return {'own_team': None, 'side_origin': 'unknown',
            'side_reason': '己方证据冲突' if hits else '未确认己方；不默认A，不计算本人胜负'}

