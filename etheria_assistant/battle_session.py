"""Connection-scoped observation lifecycle; local IDs are not protocol match IDs."""
import copy
import hashlib
import json


def battle_identity(battle):
    teams = {team:[{'id':u['hero_id'],'slot':u.get('slot'),'stats':u['stats'],
                    'effects':u['effects_raw']} for u in units] for team,units in battle['teams'].items()}
    value = [battle.get('capture_time'),teams]
    if battle.get('capture_context') == 'replay':value.append('replay')
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class BattleSession:
    def __init__(self, connection, context, emit):
        self.connection, self.context, self.emit = connection, context, emit
        self.latest = None
        self.state = 'waiting'
        self.fingerprint = None
        self.boundary_seen = False
        self.blocked = False
        self.duplicates = 0
        self.unresolved = False

    def publish(self, timestamp, state, reason):
        self.state = state
        if self.latest is None:return
        names = {'active':'战斗中 · 阵容已收到', 'awaiting_settlement':'等待结算',
                 'settled':'已结算', 'settled_unknown':'已收到结算 · 结果未知', 'incomplete':'记录不完整'}
        self.latest = copy.deepcopy(self.latest)
        self.latest['status'] = names.get(state,state)+' · '+reason
        old = self.latest.get('tracking',{})
        self.latest['tracking'] = {
            'state':state, 'reason':reason, 'connection_id':self.connection,
            'capture_context':self.context, 'roster_received':True,
            'settlement_received':old.get('settlement_received',False),
            'result_code':old.get('result_code'), 'updated_at':timestamp,
            'association_eligible':state in ('active','awaiting_settlement') and not self.blocked,
            'duplicate_openings':self.duplicates, 'protocol_match_id':None,
        }
        self.emit('battle',self.latest)

    def start(self, battle, body, timestamp):
        fingerprint = hashlib.sha256(body).hexdigest()
        if self.latest and self.state in ('active','awaiting_settlement') and not self.boundary_seen and fingerprint == self.fingerprint:
            self.duplicates += 1
            self.blocked = True
            self.publish(timestamp,self.state,'相同开场已合并；缺少协议对局ID，结算归属存在歧义')
            return False
        unresolved = self.unresolved
        if self.latest and self.state in ('active','awaiting_settlement'):
            self.publish(timestamp,'incomplete','收到下一场开场，上一场缺少结算')
        self.blocked = unresolved
        self.latest = dict(battle,capture_time=timestamp,capture_context=self.context,connection_id=self.connection)
        self.latest['record_id'] = battle_identity(self.latest)
        self.fingerprint = fingerprint; self.boundary_seen = False; self.duplicates = 0
        self.unresolved = True
        self.publish(timestamp,'active','上一场未闭合，本场结算需避免歧义' if self.blocked else
                     '回放/观战场景，不计本人战绩' if self.context=='replay' else '等待本连接结算')
        return True

    def boundary(self, timestamp):
        self.boundary_seen = True
        if self.latest and self.state == 'active':
            self.publish(timestamp,'awaiting_settlement','收到场景边界；尚未收到结算')

    def invalidate(self, timestamp, reason):
        if self.latest and self.state in ('active','awaiting_settlement'):
            self.blocked = True
            self.publish(timestamp,'incomplete',reason)

    def settle(self, code, body, timestamp):
        eligible = self.latest is not None and self.state in ('active','awaiting_settlement') and timestamp>=self.latest['capture_time']
        association = ('replay' if self.context=='replay' else 'ambiguous' if self.blocked else 'linked') if eligible else 'unlinked'
        linked = association == 'linked'
        reason = {'linked':'同一连接的当前开场', 'replay':'回放/观战，不推断本人胜负',
                  'ambiguous':'上一场缺结算，无法区分迟到结算', 'unlinked':'本连接没有可关联的完整开场'}[association]
        observation = {'schema':'etheria-settlement-observation-v2','kind':'settlement',
            'capture_time':timestamp,'body_hex':body.hex(),'result_code':code,
            'winner':{382:'A',383:'B'}.get(code,'unknown') if linked else 'unknown',
            'battle_capture_time':self.latest['capture_time'] if linked else None,
            'battle_record_id':self.latest['record_id'] if linked else None,
            'connection_id':self.connection,'capture_context':self.context,
            'association_status':association,'association_reason':reason}
        # Save the settlement before publishing the final display state.
        self.emit('observation',observation)
        if eligible:
            self.unresolved = False
            self.latest = copy.deepcopy(self.latest)
            self.latest.setdefault('tracking',{}).update(settlement_received=True,result_code=code)
            state = 'settled' if linked and code in (382,383) else 'incomplete' if association=='ambiguous' else 'settled_unknown'
            self.publish(timestamp,state,reason if not linked else '结果已关联' if code in (382,383) else f'未确认结算代码 {code}')
        elif self.state=='incomplete':
            self.unresolved = False
        return association

    def finish(self, timestamp, reason):
        self.invalidate(timestamp,reason)
