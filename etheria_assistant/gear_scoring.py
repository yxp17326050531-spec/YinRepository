"""Versioned, editable inventory scoring. Heuristic quality scores, not battle damage."""
from __future__ import annotations
import copy
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from equipment import project_gear

ROLES={'speed':'高速 / 一速','attack':'攻击输出','hp':'生命输出','defense':'防御输出',
       'survival':'生存辅助','accuracy':'命中辅助','resistance':'抵抗辅助'}
DEFAULT={
 'format':'etheria-gear-scoring','schema':1,'name':'伊瑟用途评分 · 初版','revision':'1.0-draft',
 'references':{'3':16,'7':16,'11':16,'19':14,'22':21,'25':21,'28':21,'16':19.5},
 'flat_conversion':{'4':150,'8':15,'12':10},
 'roles':{
  'attack':{'weights':{'7':1,'19':1,'22':1,'16':1},'core':['7','19','22']},
  'hp':{'weights':{'3':1,'19':1,'22':1,'16':1},'core':['3']},
  'defense':{'weights':{'11':1,'19':1,'22':1,'16':1},'core':['11']},
  'survival':{'weights':{'3':1,'11':1,'16':1},'core':['3','11']},
  'accuracy':{'weights':{'25':1,'3':1,'11':1,'16':1},'core':['25']},
  'resistance':{'weights':{'28':1,'3':1,'11':1,'16':1},'core':['28']}},
 'attribute_scale':25,'minimum_score':20,'meaningful_fraction':0.15,'minimum_attributes':2,
 'speed':{'curve':[[13.5,45],[14.5,60],[15.5,75],[16.5,90],[17.5,150],[18.5,200],[19.5,320]],
          'entry':13.5,'secondary_bonus_cap':2,
          'top':['疾驰','迅光天击','疾影强袭'],
          'second':['戍卫','奋进','浴血之躯','不屈之誓','涌泉','洞悉穿刺','狂怒','暴怒','沸腾打击','收割'],
          'top_factor':1,'second_factor':0.7,'other_factor':0.5,'two_points_factor':0.7,
          'eight_piece':['金刚','疾驰','戍卫','战意','荆棘','治愈','奋进','收割','狂怒','溢流','亵渎','逐光']}}
# Use confirmed spellings only. Different matrix names are never aliased automatically.


def default_rules():return copy.deepcopy(DEFAULT)


def number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'评分参数须为 {low}–{high} 的有限数值')
    return value


def validate_rules(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT):raise ValueError('评分预设字段不完整或含不支持字段')
    if value['format']!=DEFAULT['format'] or type(value['schema']) is not int or value['schema']!=1:raise ValueError('不支持的评分预设格式')
    for key in ('name','revision'):
        if not isinstance(value[key],str) or not 1<=len(value[key].strip())<=100:raise ValueError('请填写预设名称和规则版本')
    for key,baseline in [('references',DEFAULT['references']),('flat_conversion',DEFAULT['flat_conversion'])]:
        if not isinstance(value[key],dict) or set(value[key])!=set(baseline):raise ValueError('属性参考表字段不正确')
        for v in value[key].values():number(v,0.001,1000000)
    if not isinstance(value['roles'],dict) or set(value['roles'])!=set(DEFAULT['roles']):raise ValueError('用途类型不正确')
    for role in value['roles'].values():
        if not isinstance(role,dict) or set(role)!={'weights','core'}:raise ValueError('用途配置不正确')
        weights=role['weights'];core=role['core']
        if not isinstance(weights,dict) or not weights or not set(weights)<=set(value['references']):raise ValueError('不支持的属性权重')
        for w in weights.values():number(w,0,100)
        if not isinstance(core,list) or not core or not set(core)<=set(weights):raise ValueError('核心属性不正确')
    for key,lo,hi in [('attribute_scale',0.01,10000),('minimum_score',0,10000),('meaningful_fraction',0.001,1),('minimum_attributes',1,4)]:number(value[key],lo,hi)
    if type(value['minimum_attributes']) is not int:raise ValueError('有效属性条数须为整数')
    s=value['speed']
    if not isinstance(s,dict) or set(s)!=set(DEFAULT['speed']):raise ValueError('一速规则字段不正确')
    for key in ('top','second','eight_piece'):
        if not isinstance(s[key],list) or len(s[key])>100 or any(not isinstance(v,str) or not 1<=len(v)<=100 for v in s[key]):raise ValueError('矩阵名单不正确')
    if set(s['top']) & set(s['second']):raise ValueError('矩阵档位不能重复')
    for key in ('top_factor','second_factor','other_factor','two_points_factor'):number(s[key],0,10)
    number(s['entry'],0,100);number(s['secondary_bonus_cap'],0,10)
    curve=s['curve']
    if not isinstance(curve,list) or not 2<=len(curve)<=100:raise ValueError('速度曲线至少需要两个节点')
    lastx=-1;lasty=-1
    for pair in curve:
        if not isinstance(pair,list) or len(pair)!=2:raise ValueError('速度曲线应为[速度,分数]列表')
        x,y=pair;number(x,0,1000);number(y,0,1000000)
        if x<=lastx or y<lasty:raise ValueError('速度曲线需速度递增、分数不下降')
        lastx,lasty=x,y
    return copy.deepcopy(value)


def load_rules(path):
    if path.stat().st_size>1024*1024:raise ValueError('评分预设文件过大')
    return validate_rules(json.loads(path.read_text(encoding='utf-8-sig')))


def rounded_speed(value):return int(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def curve_score(value,curve):
    if value<curve[0][0]:return 0
    for left,right in zip(curve,curve[1:]):
        if value<=right[0]:break
    return left[1]+(value-left[0])*(right[1]-left[1])/(right[0]-left[0])


def score_gear(gear,mappings,rules,metadata=None):
    """Caller validates the selected rules once, not once per inventory row."""
    metadata=metadata or {};subs=project_gear(gear)['subs'];values={};lines=[];unknown=[]
    for a in subs:
        if a['value'] is None:unknown.append(a['type']);continue
        tag=str(a['type']);v=a['value'];equivalent=tag
        if tag in rules['flat_conversion']:
            equivalent={'4':'3','8':'7','12':'11'}[tag];v/=rules['flat_conversion'][tag]
        values[equivalent]=values.get(equivalent,0)+v
        lines.append({'name':a['name'],'value':a['value'],'unit':a['unit'],'tag':equivalent,'equivalent':v})
    complete=bool(subs) and not unknown
    matrix=gear.get('matrix') or {};name=mappings.get('matrices',{}).get(str(matrix.get('id')))
    s=rules['speed'];points=matrix.get('points')
    point_factor=1 if points==3 or (points==2 and name in s['eight_piece']) else s['two_points_factor'] if points==2 and name is not None else None
    results=[]
    for key,role in rules['roles'].items():
        contributions=[];score=0;meaningful=set()
        for line in lines:
            tag=line['tag'];w=role['weights'].get(tag,0)
            points=line['equivalent']/rules['references'][tag]*rules['attribute_scale']*w if w else 0
            contributions.append({**line,'points':points,'used':bool(w)})
            score+=points
        for tag,w in role['weights'].items():
            if w and values.get(tag,0)/rules['references'][tag]>=rules['meaningful_fraction']:meaningful.add(tag)
        eligible=score>=rules['minimum_score'] and len(meaningful)>=rules['minimum_attributes'] and bool(meaningful & set(role['core']))
        results.append({'key':key,'name':ROLES[key],'score':score*point_factor if complete and point_factor is not None else None,'partial_score':score,
                        'eligible':eligible and complete and point_factor is not None,'point_factor':point_factor,'contributions':contributions})
    speed=values.get('16')
    factor=s['top_factor'] if name in s['top'] else s['second_factor'] if name in s['second'] else s['other_factor']
    speed_ready=complete and name is not None and point_factor is not None
    eligible=speed is not None and speed>=s['entry']
    base=curve_score(speed,s['curve']) if speed is not None else 0
    bonus=min(s['secondary_bonus_cap'],sum(v/rules['references'][t] for t,v in values.items() if t!='16')) if speed is not None else 0
    total=(base+bonus)*factor*point_factor if point_factor is not None else None
    results.append({'key':'speed','name':'一速' if speed is not None and rounded_speed(speed)>=17 else '高速候选','score':total if speed_ready and eligible else None,
                    'eligible':bool(speed_ready and eligible),'speed':speed,'base':base,'bonus':bonus,'matrix':name,
                    'matrix_factor':factor,'point_factor':point_factor,'contributions':[]})
    eligible_rows=[r for r in results if r['eligible'] and r['score'] is not None]
    best=max(eligible_rows,key=lambda r:r['score']) if eligible_rows else None
    return {'roles':results,'best':best,'score':best['score'] if best else None,'complete':complete,'unknown':unknown,'revision':rules['revision']}


def score_text(result,rules):
    out=[f"评分预设：{rules['name']} · {rules['revision']}（初版启发式，非实际战斗力）",
         '用途分为有效副属性折算；当前输出/辅助不套用一速矩阵系数，主属性与配装兼容性未计入。',
         f"参考上限、用途门槛、速度曲线及其他矩阵{rules['speed']['other_factor']:g}折扣为可调整暂定值，不截断超出参考值的属性。"]
    if not result['complete']:out.append('评分不完整：存在未知或缺失副属性，暂不计入总分。')
    for r in result['roles']:
        if r['key']=='speed':
            v=r['speed'];out.append('\n一速：'+(f"{r['score']:.2f}分" if r['eligible'] else '未满足条件或矩阵信息待确认'))
            if v is not None:
                out.append(f"实际速度 {v:g} / 显示 {rounded_speed(v)}；基础 {r['base']:.2f} + 添头 {r['bonus']:.2f}，再×矩阵{r['matrix_factor']:g}×点数{r['point_factor'] if r['point_factor'] is not None else '待确认'}")
                out.append('速度只按实际数值计分，不使用强化次数；显示17速起为一速，14–16速保留高速候选评分。')
            continue
        score=r['score'];out.append(f"\n{r['name']}："+(f'{score:.2f}分' if score is not None else '不完整')+(' · 用途倾向' if r['eligible'] else ' · 未达到倾向门槛'))
        out.append(f"  有效属性小计 {r['partial_score']:.2f} × 点数系数 {r['point_factor'] if r['point_factor'] is not None else '待确认'}")
        for a in r['contributions']:
            conversion=f" → 等效{a['equivalent']:g}%" if a['name'] in ('生命','攻击','防御') else ''
            out.append(f"  {a['name']} {a['value']:g}{a['unit']}{conversion}："+(f"{a['points']:.2f}分" if a['used'] else '不计分'))
    return '\n'.join(out)
