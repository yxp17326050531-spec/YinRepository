import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from analytics import analyse, rank_statistics
from base_ui import CaptureJob
from core import Engine, Framer, load_mappings
from storage import Archive
from test_core import battle_body, blob, scalar, vi, frame


def gear_messages():
    hero = scalar(1,32601)+scalar(9,0)+scalar(7,100)+blob(10,vi(200))
    shell = scalar(1,100)+scalar(2,54432)+scalar(4,40)+blob(8,vi(3<<16|17))+blob(9,vi(42))
    gear = scalar(1,200)+scalar(2,15192)+scalar(3,15)+blob(4,b''.join(vi(x) for x in [1351680064,278881,7864448,172337,3563778]))+scalar(5,3<<16|34)+scalar(6,1)
    return [(0x1122,blob(2,hero)),(0x1129,blob(1,shell)),(0x1133,blob(1,gear))]


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.archive=Archive(self.temp.name)

    def tearDown(self):
        for handler in self.archive.logger.handlers[:]:
            handler.close();self.archive.logger.removeHandler(handler)
        self.temp.cleanup()

    def test_inventory_is_saved_before_ui_and_restored_without_attribute_guessing(self):
        observations=[]
        def emit(kind,data):
            if kind=='inventory_snapshot':
                saved=self.archive.latest_inventory()
                self.assertIsNotNone(saved)
                self.assertEqual(saved['id'],data['archive_id'])
                observations.append(data)
        job=CaptureJob(emit,20001,load_mappings(),self.archive)
        for index,(op,body) in enumerate(gear_messages()):job.engine.message(op,body,1000+index)
        saved=self.archive.latest_inventory()['data']
        self.assertEqual(len(observations),3)
        self.assertEqual(saved['gear'][0]['attributes_raw'],[1351680064,278881,7864448,172337,3563778])
        self.assertNotIn('stats',saved['gear'][0])
        self.assertEqual(saved['gear'][0]['matrix'],{'id':34,'points':3})
        self.assertEqual(saved['heroes'][0]['hero_id'],32601)  # field9=0 falls back to base id
        self.assertEqual(saved['loadout_rows'][0]['hero_id'],32601)
        self.assertEqual(saved['heroes'][0]['normal_gear_uids'],[200])
        again=copy.deepcopy(saved);again['capture_time']+=100
        again['loadout_rows'][0]['hero_name']='重新命名'
        identity=self.archive.save_inventory(again,'second')
        self.assertEqual(identity,self.archive.latest_inventory()['id'])
        self.assertEqual(self.archive.latest_inventory()['data']['capture_time'],again['capture_time'])
        # Reimporting an older identical snapshot cannot make it appear newer.
        self.archive.save_inventory(saved,'old import')
        self.assertEqual(self.archive.latest_inventory()['data']['capture_time'],again['capture_time'])
        with self.archive.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory_snapshots').fetchone()[0],3)
        # Reopening uses the same persisted immutable numeric observations.
        with closing(sqlite3.connect(self.archive.path)) as db:
            original=json.loads(db.execute('SELECT data FROM inventory_snapshots WHERE id=?',(identity,)).fetchone()[0])
        self.assertEqual(original['gear'],saved['gear'])

    def test_draft_midstream_capture_anonymized_aliases_and_idempotent_storage(self):
        events=[]
        job=CaptureJob(lambda kind,data:events.append((kind,data)),20001,load_mappings(),self.archive)
        body=scalar(1,84)+scalar(2,123456789012345)+scalar(4,234567890123456)+scalar(6,123)+scalar(8,2)+blob(9,scalar(1,40692)+scalar(4,54535))
        framer=Framer(job.engine.message,lambda text:self.fail(text))
        wire=frame(0x5fc1,body)
        framer.feed(b'broken-prefix'+wire[:9],100)
        framer.feed(wire[9:],101)
        result=self.archive.observations('draft')
        self.assertEqual(len(result),1)
        data=result[0]['data']
        self.assertEqual(data['heroes'],[{'hero_id':40692,'shell_config_id':54535}])
        self.assertEqual(data['actor_alias'],'参与者2')
        self.assertEqual(data['phase_raw'],84)
        self.assertNotIn('pick',data)
        self.assertNotIn('ban',data)
        self.assertNotIn('123456789012345',json.dumps(data))
        self.assertNotIn('234567890123456',json.dumps(data))
        job.engine.message(0x5fc1,body,101)
        self.assertEqual(len(self.archive.observations('draft')),1)
        self.assertEqual(self.archive.history()[0],0)

    def test_settlement_does_not_invent_winner_or_reuse_previous_battle(self):
        events=[]
        engine=Engine(lambda kind,data:events.append((kind,data)))
        engine.message(0x6004,scalar(1,382),100)
        first=events[-1][1]
        self.assertEqual(first['winner'],'unknown')
        self.assertIsNone(first['battle_capture_time'])
        self.assertIsNone(engine.latest)
        engine.message(0x6003,battle_body(),110)
        engine.message(0x6004,scalar(1,382),120)
        linked=[d for kind,d in events if kind=='observation'][-1]
        self.assertEqual(linked['battle_capture_time'],110)
        self.assertEqual(linked['winner'],'A')
        engine.message(0x6002,b'',130)
        engine.message(0x6004,b'',140)
        self.assertIsNone([d for kind,d in events if kind=='observation'][-1]['battle_capture_time'])

    def test_legacy_database_migration_context_backup_and_export(self):
        # Recreate the pre-2.2 database schema in a separate directory.
        directory=Path(self.temp.name)/'legacy';directory.mkdir()
        path=directory/'history.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('''CREATE TABLE battles(id TEXT PRIMARY KEY,capture_time REAL,saved_at TEXT NOT NULL,
                source TEXT NOT NULL,status TEXT NOT NULL,original TEXT NOT NULL,opponent TEXT NOT NULL DEFAULT '待选择')''')
            battle={'capture_time':100,'status':'对局数据已到达','teams':{'A':[],'B':[]}}
            db.execute('INSERT INTO battles VALUES (?,?,?,?,?,?,?)',('legacy',100,'old','old','old',json.dumps(battle),'待选择'))
        archive=Archive(directory)
        self.addCleanup(lambda:[(h.close(),archive.logger.removeHandler(h)) for h in archive.logger.handlers[:]])
        self.assertEqual(archive.get('legacy')['original'],battle)
        self.assertEqual(archive.context('legacy')['winner'],'unknown')
        archive.set_context('legacy','A','BP排位','SS6')
        archive.save_observation({'kind':'draft','capture_time':101,'heroes':[]},'test')
        archive.save_inventory({'capture_time':102,'gear':[]},'test')
        dataset=archive.dataset()
        self.assertEqual(dataset['battles'][0]['original'],battle)
        self.assertEqual(dataset['battles'][0]['sample_kind'],'BP排位')
        self.assertEqual(dataset['battles'][0]['winner'],'A')
        self.assertEqual(dataset['battles'][0]['result_origin'],'manual')
        self.assertEqual(len(dataset['observations']),1)
        archive.set_opponent('legacy','B 队')
        archive.save_observation({'kind':'settlement','capture_time':103,'body_hex':'00','winner':'unknown','battle_capture_time':100},'test')
        verification=archive.validation_dataset()
        self.assertEqual(verification['schema'],'etheria-result-validation-v1')
        self.assertEqual(verification['battles'][0]['opponent'],'B 队')
        self.assertEqual(verification['battles'][0]['winner'],'A')
        self.assertEqual([r['kind'] for r in verification['observations']],['settlement'])
        with self.assertRaises(ValueError):archive.set_context('legacy','win','BP排位')
        with self.assertRaises(ValueError):archive.set_context('legacy','A','猜测排位')
        dest=Path(self.temp.name)/'backup.sqlite3';archive.backup(dest)
        with closing(sqlite3.connect(dest)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT winner FROM battle_context').fetchone()[0],'A')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory_snapshots').fetchone()[0],1)

    def test_statistics_denominators_unknown_draws_groups_and_training(self):
        def match(winner,kind='BP排位',group='SS6',a=(1,2),b=(1,3)):
            return {'winner':winner,'sample_kind':kind,'dataset_group':group,
                    'original':{'teams':{'A':[{'hero_id':i} for i in a],'B':[{'hero_id':i} for i in b]}}}
        battles=[match('A',a=(1,1,2)),match('unknown',a=(2,),b=(3,)),match('draw',a=(2,),b=(3,)),
                 match('B','练习/测试'),match('A','竞技场'),match('B',group='SS5')]
        original=copy.deepcopy(battles)
        result=analyse({'battles':battles},{'heroes':{'2':'测试角色'}},dataset_group='SS6')
        self.assertEqual(result['eligible_matches'],3)
        self.assertEqual(result['team_samples'],6)
        self.assertEqual(result['decided_matches'],1)
        heroes={r['hero_id']:r for r in result['heroes']}
        self.assertEqual(heroes[1]['appearances'],2)
        self.assertEqual(heroes[1]['win_rate'],0.5)
        self.assertEqual(heroes[2]['appearances'],3)
        self.assertEqual(heroes[2]['team_appearance_rate'],0.5)
        self.assertEqual(heroes[2]['decided'],1)
        self.assertEqual(heroes[2]['win_rate'],1)
        self.assertEqual(heroes[2]['unknown'],1)
        self.assertEqual(heroes[2]['draws'],1)
        self.assertEqual(heroes[2]['hero_name'],'测试角色')
        self.assertEqual(result['cooccurrences'][0]['hero_ids'],[1,2])
        unknown=analyse({'battles':[match('unknown')]},{'heroes':{}})
        self.assertTrue(all(r['win_rate'] is None for r in unknown['heroes']))
        self.assertEqual(battles,original)
        self.assertEqual(analyse({'battles':battles},{'heroes':{}},dataset_group='missing')['heroes'],[])

    def test_official_catalogue_adds_exact_names_without_suffix_guesses(self):
        mappings=load_mappings()
        catalogue=json.loads(Path(__file__).with_name('hero_catalogue.json').read_text(encoding='utf-8'))
        self.assertEqual(len(catalogue['exact_id_records']),91)
        self.assertEqual(mappings['heroes']['32051'],'克索司')
        self.assertEqual(mappings['heroes']['32101'],'斐莫莉安')
        self.assertEqual(mappings['heroes']['32102'],'斐莫莉安')
        self.assertNotIn('32109',mappings['heroes'])

    def test_matchup_direction_mirrors_and_own_perspective(self):
        def match(winner,opponent='B 队'):
            return {'winner':winner,'sample_kind':'BP排位','dataset_group':'', 'opponent':opponent,
                    'original':{'teams':{'A':[{'hero_id':1},{'hero_id':2},{'hero_id':2}],
                                         'B':[{'hero_id':1},{'hero_id':3}]}}}
        data={'battles':[match('A'),match('B'),match('unknown'),match('draw')]}
        saved=copy.deepcopy(data)
        result=analyse(data,{'heroes':{}})
        by_pair={(r['hero_id'],r['opponent_id']):r for r in result['matchups']}
        self.assertNotIn((1,1),by_pair)
        self.assertEqual(by_pair[(2,3)]['appearances'],4)
        self.assertEqual(by_pair[(2,3)]['wins'],1)
        self.assertEqual(by_pair[(2,3)]['losses'],1)
        self.assertEqual(by_pair[(2,3)]['draws'],1)
        self.assertEqual(by_pair[(2,3)]['unknown'],1)
        self.assertEqual(by_pair[(2,3)]['decided'],2)
        self.assertEqual(by_pair[(2,3)]['win_rate'],0.5)
        self.assertEqual(by_pair[(3,2)]['win_rate'],0.5)
        own=analyse(data,{'heroes':{}},perspective='own')
        self.assertEqual(own['eligible_matches'],4)
        self.assertEqual(own['team_samples'],4)
        self.assertEqual({(r['hero_id'],r['opponent_id']) for r in own['matchups']},{(1,3),(2,1),(2,3)})
        self.assertEqual([r['hero_ids'] for r in own['cooccurrences']],[[1,2]])
        self.assertEqual(analyse({'battles':[match('A','待选择')]},{'heroes':{}},perspective='own')['eligible_matches'],1)
        switched=analyse({'battles':[match('B','A 队')]},{'heroes':{}},perspective='own')
        self.assertEqual({r['hero_id'] for r in switched['heroes']},{1,2})
        self.assertTrue(all(r['losses']==1 for r in switched['heroes']))
        self.assertEqual(data,saved)

    def test_rankings_filter_qualified_samples_and_sort_in_correct_direction(self):
        def row(hero,enemy,wins,losses):
            return {'hero_id':hero,'opponent_id':enemy,'wins':wins,'losses':losses,
                    'decided':wins+losses,'win_rate':wins/(wins+losses) if wins+losses else None}
        result={'matchups':[row(1,2,1,4),row(1,3,2,8),row(1,4,5,0),row(2,1,4,1),row(1,5,0,0)],
                'cooccurrences':[{'hero_ids':[1,2],'decided':1,'win_rate':1.0},
                                 {'hero_ids':[1,3],'decided':10,'win_rate':0.8},
                                 {'hero_ids':[2,4],'decided':20,'win_rate':0.9},
                                 {'hero_ids':[1,5],'decided':20,'win_rate':0.8}]}
        original=copy.deepcopy(result)
        rows=rank_statistics(result,'matchups',1,5)
        self.assertEqual([r['opponent_id'] for r in rows],[3,2,4])
        self.assertEqual([r['hero_ids'] for r in rank_statistics(result,'cooccurrences',1,5)],[[1,5],[1,3]])
        self.assertEqual([r['hero_ids'] for r in rank_statistics(result,'cooccurrences',None,1)][0],[1,2])
        self.assertEqual(result,original)
        with self.assertRaises(ValueError):rank_statistics(result,'matchups',min_decided=0)


if __name__=='__main__':unittest.main()
