"""Connection-local player evidence. Raw account IDs never leave this object."""
import hashlib


class PlayerEvidence:
    def __init__(self, fields, record):
        self.fields, self.record = fields, record
        self.reset()

    def reset(self):
        self.selections = {}
        self.players = []
        self.ratings = {}
        self.header_time = None
        self.draft_time = None
        self.bound = False

    def draft(self, body, timestamp):
        if self.bound:
            self.reset()
        r = self.record(body)
        # Only observed confirmation states, never previews or array position.
        if r.get(1) not in (85, 101) or not isinstance(r.get(4), int):
            return
        heroes = [self.record(v).get(1) for f, w, v in self.fields(body) if f == 9 and w == 2]
        if heroes and all(type(h) is int and h > 0 for h in heroes):
            self.selections.setdefault(r[4], set()).update(heroes)
            self.draft_time = timestamp

    def header(self, body, timestamp):
        if self.bound or self.header_time is not None:
            self.reset()
        self.players = []
        self.header_time = timestamp
        header = self.record(body).get(1)
        if not isinstance(header, bytes):
            return
        for f, w, value in self.fields(header):
            if f != 8 or w != 2:
                continue
            entry = self.record(value)
            profile = entry.get(1)
            if not isinstance(profile, bytes):
                continue
            r = self.record(profile)
            uid, raw_name = r.get(1), r.get(3)
            if type(uid) is not int or uid <= 0 or not isinstance(raw_name, bytes) or len(raw_name) > 256:
                continue
            try:
                name = raw_name.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if name and len(name) <= 64 and all(c.isprintable() for c in name):
                self.players.append((uid, name))
                if all(type(entry.get(k)) is int and entry[k]>0 for k in (2,3)):
                    self.ratings[uid]={'opening_rating':entry[2],'opening_rank':entry[3]}
        if len(self.players) != 2 or len({uid for uid, _ in self.players}) != 2:
            self.players = []

    def decorate(self, battle, timestamp):
        was_bound=self.bound
        self.bound = True
        recent=self.draft_time is not None and 0<=timestamp-self.draft_time<=300
        if recent and not was_bound:
            teams={t:{u['hero_id'] for u in units} for t,units in battle['teams'].items()}
            confirmed={t:[] for t in ('A','B')}
            for uid,selections in self.selections.items():
                for t in ('A','B'):
                    if len(selections & teams[t])>=2 and not selections & teams['B' if t=='A' else 'A']:
                        confirmed[t].append(uid)
            if all(len(confirmed[t])==1 for t in ('A','B')) and confirmed['A']!=confirmed['B']:
                battle['draft_evidence']={'source':'0x5fc1','confirmed_teams':['A','B']}
        if self.header_time is None or not 0 <= timestamp - self.header_time <= 60:
            return
        teams = {t: {u['hero_id'] for u in units} for t, units in battle['teams'].items()}
        recent = self.draft_time is not None and 0 <= timestamp - self.draft_time <= 300
        players = []
        for uid, name in self.players:
            confirmed = self.selections.get(uid, set()) if recent else set()
            matches = [t for t, heroes in teams.items() if len(heroes & confirmed) >= 2
                       and not confirmed & teams['B' if t == 'A' else 'A']]
            team = matches[0] if len(matches) == 1 else None
            key = hashlib.sha256(('etheria-player-v1:' + str(uid)).encode()).hexdigest()
            players.append({'nickname': name, 'team': team, 'player_key': key, **self.ratings.get(uid,{})})
        # Conflicting bindings cannot identify either side.
        bound = [p['team'] for p in players if p['team']]
        if len(bound) != len(set(bound)):
            for p in players:
                p['team'] = None
        if players:
            battle['participants'] = [{k: v for k, v in p.items() if k != 'player_key'} for p in players]
            battle['participant_status'] = ('玩家方向已由确认选人和上场阵容交叉对应'
                if len(bound) == 2 and len(set(bound)) == 2 else '昵称已读取；对应A/B关系证据不足')
            # CaptureJob stores keys in a separate local table and strips this
            # private transport field before UI events, original records/export.
            battle['_local_players'] = players

