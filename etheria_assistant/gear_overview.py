"""Read-only inventory overview metrics; fixed reference radar, never a population rank."""
import math
from gear_scoring import rounded_speed

AXES=(('speed','速度'),('attack','攻击输出'),('hp','生命输出'),('defense','防御输出'),
      ('survival','生存辅助'),('support','命中 / 抵抗'))


def top_count(value):
    return value if type(value) is int and 1<=value<=20 else 5


def overview_metrics(scores,rules,n=5):
    n=top_count(n);items=list(scores.values());axes=[]
    for key,name in AXES:
        values=[]
        for item in items:
            candidates=[r['score'] for r in item['roles'] if r['eligible'] and r['score'] is not None
                        and (r['key'] in ('accuracy','resistance') if key=='support' else r['key']==key)]
            if candidates:values.append(max(candidates))
        values.sort(reverse=True);chosen=values[:n];raw=sum(chosen)
        if key=='speed':
            s=rules['speed'];single=(s['curve'][-1][1]+s['secondary_bonus_cap'])*max(s['top_factor'],s['second_factor'],s['other_factor'])*max(1,s['two_points_factor'])
        else:
            keys=('accuracy','resistance') if key=='support' else (key,)
            single=max(sum(rules['roles'][k]['weights'].values())*rules['attribute_scale'] for k in keys)*max(1,rules['speed']['two_points_factor'])
        reference=single*n
        percent=raw/reference*100 if reference>0 else None
        axes.append({'key':key,'name':name,'raw':raw,'reference':reference,'percent':percent,
                     'draw_percent':min(100,max(0,percent)) if percent is not None else 0,'count':len(chosen)})
    bins={key:0 for key in ('低于14','14–16','17','18','19','20+')};unknown_speed=0
    for item in items:
        speed=next((r.get('speed') for r in item['roles'] if r['key']=='speed'),None)
        if speed is None:unknown_speed+=1;continue
        display=rounded_speed(speed)
        bucket='低于14' if display<14 else '14–16' if display<17 else str(display) if display<20 else '20+'
        bins[bucket]+=1
    return {'total':sum(i['score'] or 0 for i in items),'count':len(items),
            'rated':sum(i['score'] is not None for i in items),'incomplete':sum(not i['complete'] for i in items),
            'axes':axes,'speed_bins':bins,'unknown_speed':unknown_speed,'top_n':n}
