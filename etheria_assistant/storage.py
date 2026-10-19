"""Local archive. Original observations and manual annotations are separate."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import uuid
from core import shell_effect_mapping, record
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def data_directory():
    base = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else os.environ.get('XDG_DATA_HOME')
    return (Path(base) if base else Path.home() / '.local' / 'share') / 'EtheriaAssistant'


def unit_key(team, index, unit):
    return f"{team}:{index}:{unit['hero_id']}"


def battle_key(battle):
    # Names/mapping versions must not create duplicate records for the same observation.
    teams = {team: [{'id': u['hero_id'], 'slot': u.get('slot'), 'stats': u['stats'],
                     'effects': u['effects_raw']} for u in units] for team, units in battle['teams'].items()}
    return hashlib.sha256(encode([battle.get('capture_time'), teams]).encode()).hexdigest()


class Archive:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'history.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS battles (
                    id TEXT PRIMARY KEY, capture_time REAL, saved_at TEXT NOT NULL,
                    source TEXT NOT NULL, status TEXT NOT NULL, original TEXT NOT NULL,
                    opponent TEXT NOT NULL DEFAULT '待选择');
                CREATE TABLE IF NOT EXISTS annotations (
                    battle_id TEXT NOT NULL REFERENCES battles(id), unit_key TEXT NOT NULL,
                    value TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(battle_id, unit_key));
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mappings (
                    category TEXT NOT NULL, id TEXT NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY(category, id));
                CREATE TABLE IF NOT EXISTS audit (
                    time TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS battle_context (
                    battle_id TEXT PRIMARY KEY REFERENCES battles(id),
                    winner TEXT NOT NULL, sample_kind TEXT NOT NULL,
                    dataset_group TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS inventory_snapshots (
                    id TEXT PRIMARY KEY, capture_time REAL, saved_at TEXT NOT NULL,
                    source TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY, capture_time REAL, kind TEXT NOT NULL,
                    source TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS automatic_results (
                    battle_id TEXT PRIMARY KEY REFERENCES battles(id),
                    winner TEXT NOT NULL, observation_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS battle_trash (
                    battle_id TEXT PRIMARY KEY REFERENCES battles(id),
                    deleted_at TEXT NOT NULL, batch_id TEXT NOT NULL);
            ''')
        # Replay saved observations once so old captures gain automatic results too.
        with self.connect() as db:
            for row in db.execute("SELECT id,data,source FROM observations WHERE kind='settlement'").fetchall():
                self._apply_settlement(db,json.loads(row['data']),row['source'],row['id'])
        self.logger = logging.getLogger('etheria.' + str(self.path))
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = RotatingFileHandler(self.directory / 'runtime.log', maxBytes=2*1024*1024, backupCount=3, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            self.logger.addHandler(handler)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connect() as db:
            return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}

    def save_settings(self, values):
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)', [(k, encode(v)) for k, v in values.items()])

    def save_battle(self, battle, source):
        bid = battle_key(battle)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO battles(id,capture_time,saved_at,source,status,original) VALUES (?,?,?,?,?,?)',
                       (bid, battle.get('capture_time'), now(), source, battle['status'], encode(battle)))
            db.execute('UPDATE battles SET status=? WHERE id=?', (battle['status'], bid))
        return bid

    def history(self, limit=100, offset=0):
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM battles WHERE id NOT IN (SELECT battle_id FROM battle_trash)').fetchone()[0]
            rows = [dict(r) for r in db.execute('SELECT id,capture_time,saved_at,source,status,opponent FROM battles WHERE id NOT IN (SELECT battle_id FROM battle_trash) ORDER BY capture_time DESC,id LIMIT ? OFFSET ?', (limit, offset))]
        return total, rows

    def is_deleted(self, bid):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM battle_trash WHERE battle_id=?',(bid,)).fetchone() is not None

    def trash_battles(self, identifiers):
        identifiers=list(dict.fromkeys(identifiers))
        batch=uuid.uuid4().hex
        stamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        changed=[]
        with self.connect() as db:
            for bid in identifiers:
                if db.execute('SELECT 1 FROM battles WHERE id=?',(bid,)).fetchone() is None:
                    continue
                cursor=db.execute('INSERT OR IGNORE INTO battle_trash VALUES (?,?,?)',(bid,stamp,batch))
                if cursor.rowcount:changed.append(bid)
            if changed:
                db.execute('INSERT INTO audit VALUES (?,?,?,?)',(now(),'trash_battles',batch,encode(changed)))
        return changed

    def restore_last_trash(self):
        with self.connect() as db:
            row=db.execute('SELECT batch_id FROM battle_trash ORDER BY deleted_at DESC LIMIT 1').fetchone()
            if not row:return []
            batch=row['batch_id']
            identifiers=[r['battle_id'] for r in db.execute('SELECT battle_id FROM battle_trash WHERE batch_id=?',(batch,))]
            db.execute('DELETE FROM battle_trash WHERE batch_id=?',(batch,))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)',(now(),'restore_trash',batch,encode(identifiers)))
        return identifiers

    def get(self, bid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM battles WHERE id=?', (bid,)).fetchone()
            if row is None:
                raise ValueError('找不到这场对局')
            annotations = {r['unit_key']: json.loads(r['value']) for r in db.execute('SELECT * FROM annotations WHERE battle_id=?', (bid,))}
        return {'id': bid, 'original': json.loads(row['original']), 'status': row['status'],
                'source': row['source'], 'opponent': row['opponent'], 'annotations': annotations}

    def set_opponent(self, bid, value):
        if value not in ('待选择', 'A 队', 'B 队'):
            raise ValueError('无效队伍')
        with self.connect() as db:
            db.execute('UPDATE battles SET opponent=? WHERE id=?', (value, bid))

    def annotate(self, bid, key, shell=None, matrices=None, note=''):
        battle = self.get(bid)['original']
        valid = {unit_key(t, i, u) for t, units in battle['teams'].items() for i, u in enumerate(units)}
        if key not in valid:
            raise ValueError('该角色不属于这场对局')
        if shell is not None and (not shell.strip() or len(shell) > 100):
            raise ValueError('智壳名称不能为空，最多 100 字')
        if matrices is not None:
            if len(matrices) > 12:
                raise ValueError('最多填写 12 项矩阵')
            for m in matrices:
                if not m.get('name', '').strip() or len(m['name']) > 100:
                    raise ValueError('请填写矩阵名称')
                if type(m.get('points')) is not int or not 0 <= m['points'] <= 999:
                    raise ValueError('矩阵点数应为 0–999 的整数')
        if len(note) > 2000:
            raise ValueError('备注最多 2000 字')
        value = {'shell': shell.strip() if shell else None, 'matrices': matrices, 'note': note,
                 'origin': 'manual', 'updated_at': now()}
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO annotations VALUES (?,?,?,?)', (bid, key, encode(value), now()))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)', (now(), 'annotation', bid + '/' + key, encode(value)))

    def clear_annotation(self, bid, key):
        with self.connect() as db:
            db.execute('DELETE FROM annotations WHERE battle_id=? AND unit_key=?', (bid, key))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)', (now(), 'clear_annotation', bid + '/' + key, '{}'))

    def mappings(self, builtin):
        result = copy.deepcopy(builtin)
        with self.connect() as db:
            for row in db.execute('SELECT * FROM mappings'):
                result[row['category']][row['id']] = json.loads(row['value'])
                if row['category'] == 'matrices':
                    result.get('matrix_confidence', {}).pop(row['id'],None)
        return result

    def set_mapping(self, category, identifier, name, threshold=None):
        if category not in ('heroes','shell_configs','shell_effects','matrices','matrix_effects'):
            raise ValueError('未知映射类型')
        identifier = str(int(identifier))
        if not 0 < int(identifier) < 2**64:
            raise ValueError('编号应为正整数')
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError('名称不能为空，最多 100 字')
        value = name
        if category in ('shell_effects', 'matrix_effects'):
            value = {'name': name, 'confidence': '用户映射'}
        if category == 'matrix_effects':
            threshold = int(threshold)
            if not 1 <= threshold <= 999:
                raise ValueError('效果档位应为 1–999 点')
            value['threshold'] = threshold
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?)', (category, identifier, encode(value)))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)', (now(), 'mapping', category + '/' + identifier, encode(value)))

    def remove_mapping(self, category, identifier):
        with self.connect() as db:
            db.execute('DELETE FROM mappings WHERE category=? AND id=?', (category, str(int(identifier))))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)', (now(), 'restore_mapping', category + '/' + str(identifier), '{}'))

    def backup(self, destination):
        if Path(destination).resolve() == self.path.resolve():
            raise ValueError('备份位置不能是当前数据库本身')
        with self.connect() as db:
            target = sqlite3.connect(destination)
            try:
                db.backup(target)
            finally:
                target.close()

    def context(self, bid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM battle_context WHERE battle_id=?',(bid,)).fetchone()
            automatic = db.execute('SELECT winner FROM automatic_results WHERE battle_id=?',(bid,)).fetchone()
        context = dict(row) if row else {'winner':'unknown','sample_kind':'未分类','dataset_group':''}
        context['result_origin'] = 'manual' if context['winner'] != 'unknown' else 'unknown'
        if automatic:
            context.update(winner=automatic['winner'],result_origin='automatic')
        return context

    def set_classification(self, bid, sample_kind, dataset_group=''):
        # Retain old manual metadata for compatibility; results have no UI editor.
        with self.connect() as db:
            row=db.execute('SELECT winner FROM battle_context WHERE battle_id=?',(bid,)).fetchone()
        self.set_context(bid,row['winner'] if row else 'unknown',sample_kind,dataset_group)

    @staticmethod
    def _apply_settlement(db, data, source, observation_id):
        if data.get('kind') != 'settlement' or data.get('battle_capture_time') is None:
            return
        try:
            code=record(bytes.fromhex(data.get('body_hex',''))).get(1)
        except (ValueError,TypeError,OverflowError):
            return
        winner={382:'A',383:'B'}.get(code)
        if winner is None:
            return
        capture_time=data.get('capture_time')
        if not isinstance(capture_time,(int,float)) or capture_time < data['battle_capture_time']:
            return
        matches=db.execute('SELECT id FROM battles WHERE capture_time=? AND source=?',
                           (data['battle_capture_time'],source)).fetchall()
        if len(matches)!=1:
            return
        bid=matches[0]['id']
        previous=db.execute('SELECT winner FROM automatic_results WHERE battle_id=?',(bid,)).fetchone()
        if previous and previous['winner']!=winner:
            winner='unknown'  # Conflicting linked settlements never silently flip a result.
        db.execute('INSERT OR REPLACE INTO automatic_results VALUES (?,?,?)',(bid,winner,observation_id))

    def set_context(self, bid, winner, sample_kind, dataset_group=''):
        if winner not in ('unknown','A','B','draw'):
            raise ValueError('无效胜负')
        if sample_kind not in ('未分类','BP排位','竞技场','练习/测试'):
            raise ValueError('无效对局分类')
        if len(dataset_group.strip()) > 100:
            raise ValueError('统计分组最多100字')
        self.get(bid)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO battle_context VALUES (?,?,?,?,?)',
                       (bid,winner,sample_kind,dataset_group.strip(),now()))
            db.execute('INSERT INTO audit VALUES (?,?,?,?)',(now(),'context',bid,
                       encode({'winner':winner,'sample_kind':sample_kind,'dataset_group':dataset_group.strip(),'origin':'manual'})))

    def save_inventory(self, snapshot, source):
        content = {k:v for k,v in snapshot.items() if k not in ('capture_time','archive_id','loadout_rows')}
        identity = hashlib.sha256(encode(content).encode()).hexdigest()
        with self.connect() as db:
            db.execute('''INSERT INTO inventory_snapshots VALUES (?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET capture_time=excluded.capture_time,
                       saved_at=excluded.saved_at,source=excluded.source,data=excluded.data
                       WHERE COALESCE(excluded.capture_time,-1)>=COALESCE(inventory_snapshots.capture_time,-1)''',
                       (identity,snapshot.get('capture_time'),now(),source,encode(snapshot)))
        return identity

    def latest_inventory(self):
        with self.connect() as db:
            row = db.execute('SELECT * FROM inventory_snapshots ORDER BY capture_time DESC,saved_at DESC LIMIT 1').fetchone()
        return {'id':row['id'],'source':row['source'],'data':json.loads(row['data'])} if row else None

    def save_observation(self, observation, source):
        data = {k:v for k,v in observation.items() if k != 'archive_id'}
        identity = hashlib.sha256(encode(data).encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?)',
                       (identity,data.get('capture_time'),data['kind'],source,encode(data)))
            self._apply_settlement(db,data,source,identity)
        return identity

    def observations(self, kind=None, limit=300):
        with self.connect() as db:
            deleted_times={r[0] for r in db.execute('SELECT b.capture_time FROM battles b JOIN battle_trash t ON b.id=t.battle_id')}
            if kind:
                rows = db.execute('SELECT * FROM observations WHERE kind=? ORDER BY capture_time DESC',(kind,))
            else:
                rows = db.execute('SELECT * FROM observations ORDER BY capture_time DESC')
            out=[]
            for row in rows:
                data=json.loads(row['data'])
                if data.get('battle_capture_time') is not None and data['battle_capture_time'] in deleted_times:
                    continue
                out.append(dict(row,data=data))
                if len(out)>=limit:break
        return out

    def dataset(self):
        """An explicit local export; never an upload or fabricated BP sequence."""
        with self.connect() as db:
            rows = db.execute('''SELECT b.id,b.original,b.opponent,c.winner,c.sample_kind,c.dataset_group
                   FROM battles b LEFT JOIN battle_context c ON c.battle_id=b.id
                   WHERE b.id NOT IN (SELECT battle_id FROM battle_trash) ORDER BY b.capture_time''').fetchall()
            observations = db.execute('SELECT id,data FROM observations ORDER BY capture_time').fetchall()
            deleted_times={r[0] for r in db.execute('SELECT b.capture_time FROM battles b JOIN battle_trash t ON b.id=t.battle_id')}
        observation_rows=[]
        for row in observations:
            data=json.loads(row['data'])
            if data.get('battle_capture_time') is not None and data['battle_capture_time'] in deleted_times:
                continue
            observation_rows.append({'id':row['id'],**data})
        return {'schema':'etheria-analysis-dataset-v1','exported_at':now(),
                'battles':[{'id':r['id'],'original':json.loads(r['original']),
                            'opponent':'B 队',
                            'winner':self.context(r['id'])['winner'],'result_origin':self.context(r['id'])['result_origin'],
                            'sample_kind':r['sample_kind'] or '未分类','dataset_group':r['dataset_group'] or ''} for r in rows],
                'observations':observation_rows,
                'notes':['BP观测未确认预选/选取/禁用含义，未关联具体对局，不能计算pick/ban率。',
                         '阵容出场率分母为符合筛选条件的队伍数；未知胜负不计入胜率。',
                         '己方固定A、敌方固定B；已关联结算382=胜、383=负，其他结果未知；类型及分组手动维护。']}

    def validation_dataset(self):
        dataset=self.dataset()
        return {**dataset,'schema':'etheria-result-validation-v1',
                'observations':[r for r in dataset['observations'] if r['kind']=='settlement'],
                'notes':['己方固定A，敌方固定B；382=胜、383=负。',
                         '自动结果要求精确关联；未知和冲突结算不计入胜率。']}

    def shell_catalogue(self, mappings):
        """Observed candidate effects, deduplicated; range is a heuristic only."""
        seen = {}
        with self.connect() as db:
            for row in db.execute('SELECT id,original FROM battles WHERE id NOT IN (SELECT battle_id FROM battle_trash)'):
                battle = json.loads(row['original'])
                for units in battle['teams'].values():
                    for unit in units:
                        for effect in shell_candidates(unit, mappings):
                            item = seen.setdefault(effect, {'id': effect, 'observations': 0, 'battles': set(), 'heroes': set()})
                            item['observations'] += 1
                            item['battles'].add(row['id'])
                            item['heroes'].add(mappings['heroes'].get(str(unit['hero_id']), f"角色 #{unit['hero_id']}"))
        out = []
        for effect, item in sorted(seen.items()):
            name = shell_effect_mapping(mappings, effect)
            out.append({'id': effect, 'name': name['name'] if name else '',
                        'status': name.get('confidence', '已命名') if name else '候选编号；待确认',
                        'observations': item['observations'], 'battle_count': len(item['battles']),
                        'heroes': sorted(item['heroes'])})
        return out


def shell_candidates(unit, mappings):
    return sorted({effect for effect in unit['effects_raw']
                   if str(effect) in mappings['shell_effects'] or 38_000_000 <= effect < 40_000_000})


def project_unit(unit, mappings, annotation=None):
    """Re-label a copy; never alter captured data or infer a complete loadout."""
    out = copy.deepcopy(unit)
    out['hero_name'] = mappings['heroes'].get(str(unit['hero_id']), f"角色 #{unit['hero_id']}")
    out['shells'] = []
    out['matrix_effects_candidates'] = []
    for effect in unit['effects_raw']:
        shell = shell_effect_mapping(mappings, effect)
        if shell and shell not in out['shells']:
            out['shells'].append(copy.deepcopy(shell))
        matrix = mappings['matrix_effects'].get(str(effect))
        if matrix:
            out['matrix_effects_candidates'].append(dict(matrix, effect_id=effect))
    out['manual'] = copy.deepcopy(annotation) if annotation else None
    return out
