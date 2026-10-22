"""Conservative result projection from matched opening and settlement ratings."""
import re
from core import fields


def own_nickname_side(name, participants):
    name=name.strip()
    def matches(observed):
        if '#' in name:return observed==name
        return re.sub(r'#[0-9]+$','',observed)==name
    hits=[p for p in participants if matches(p.get('nickname',''))]
    return hits[0].get('team') if name and len(hits)==1 and hits[0].get('team') in ('A','B') else None


def unique_record(body):
    result={}
    for field,wire,value in fields(body):
        if field in result:raise ValueError('重复结算字段')
        result[field]=value
    return result


def rating_result(opening, body):
    if opening.get('capture_context')!='live' or opening.get('source_opcode')!='0x6003':return None
    try:
        end=unique_record(body)
        match_id=opening.get('protocol_match_id')
        if type(match_id) is not int or match_id<=0 or end.get(8)!=match_id:return None
        if type(opening.get('protocol_context')) is not int or end.get(6)!=opening['protocol_context']:return None
        score=unique_record(end[7])
        if any(type(score.get(k)) is not int or score[k]<=0 for k in (1,2,3,4)):return None
        # Promotion/demotion and protected/unchanged ratings require samples.
        if score[1]!=score[2] or score[3]==score[4]:return None
        players=opening.get('participants',[])
        if len(players)!=2 or {p.get('team') for p in players}!={'A','B'}:return None
        if any(type(p.get('opening_rating')) is not int or type(p.get('opening_rank')) is not int for p in players):return None
        hits=[p for p in players if p['opening_rating']==score[3] and p['opening_rank']==score[1]]
        if len(hits)!=1:return None
        team=hits[0]['team'];delta=score[4]-score[3]
        return {'winner':team if delta>0 else ('B' if team=='A' else 'A'),
                'rated_team':team,'before':score[3],'after':score[4],'delta':delta,
                'reason':'本场编号一致；开场积分唯一对应玩家，结算积分增减判定'}
    except (KeyError,ValueError,TypeError,OverflowError):return None
