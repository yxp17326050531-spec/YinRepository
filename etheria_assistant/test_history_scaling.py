"""Pagination, nickname search and automatic-mode regressions with synthetic data."""
import copy
import json
import tempfile
import unittest
from analytics import analyse
from battle_metadata import mode_info
from core import load_mappings,Engine
from storage import Archive,encode
from test_battle_metadata import unique_battle
from test_core import scalar,blob
from test_player_identity import roster


class HistoryScalingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.archive=Archive(self.temp.name)
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.temp.cleanup()
    def battle(self,stamp=100,sizes=(4,4),name='Target#1234'):
        battle=unique_battle(stamp)
        for t,size in zip(('A','B'),sizes):
            units=battle['teams'][t];battle['teams'][t]=[copy.deepcopy(units[i%4]) for i in range(size)]
        battle['participants']=[{'nickname':name,'team':'A'},{'nickname':'Other#5678','team':'B'}]
        return battle
    def test_requested_size_rules_confirmed_draft_replay_and_manual_override(self):
        for sizes,kind in (((3,3),'GVG'),((4,1),'PVE'),((5,5),'PVE'),((4,4),'未分类')):
            self.assertEqual(mode_info(self.battle(sizes=sizes))['kind'],kind)
        battle=self.battle();battle['draft_evidence']={'confirmed_teams':['A','B']}
        self.assertEqual(mode_info(battle)['kind'],'BP排位')
        battle['capture_context']='replay';self.assertEqual(mode_info(battle)['kind'],'回放/观战')
        bid=self.archive.save_battle(self.battle(sizes=(3,3)),'test')
        self.archive.classify_battles([bid],'练习/测试')
        self.assertEqual(self.archive.history(sample_kind='练习/测试')[0],1)
        self.archive.classify_battles([bid],'未分类')
        self.assertEqual(self.archive.history(sample_kind='GVG')[0],1)

    def test_confirmed_draft_requires_recent_matching_both_teams_on_same_connection(self):
        for preview,stale,other,one,expected in ((False,False,False,False,'BP排位'),
                (True,False,False,False,'未分类'),(False,True,False,False,'未分类'),
                (False,False,True,False,'未分类'),(False,False,False,True,'未分类')):
            engine=Engine(lambda *a:None)
            for uid,heroes in ((111111111,(11,12)),(222222222,(21,22))):
                for hero in heroes[:1] if one else heroes:
                    engine.message(0x5fc1,scalar(1,84 if preview else 85)+scalar(4,uid)+blob(9,scalar(1,hero)),10,'one')
            engine.message(0x6003,roster(),500 if stale else 20,'two' if other else 'one')
            self.assertEqual(engine.latest['mode_detection']['kind'],expected)

    def test_legacy_draft_evidence_and_personal_replay_filter_stay_consistent(self):
        b=self.battle();b['participant_status']='玩家方向已由确认选人和上场阵容交叉对应'
        bid=self.archive.save_battle(b,'legacy')
        self.assertEqual(self.archive.history(sample_kind='BP排位')[0],1)
        self.assertNotIn('draft_evidence',self.archive.get(bid)['original'])
        replay=self.battle(200);replay['capture_context']='replay'
        rid=self.archive.save_battle(replay,'replay');self.archive.set_classification(rid,'BP排位')
        self.archive.set_review(rid,own_replay=True)
        self.assertEqual(self.archive.history(sample_kind='BP排位')[0],1)
        self.assertEqual(self.archive.history(sample_kind='回放/观战')[0],1)
        self.archive.set_perspective(rid,'A')
        self.assertEqual(self.archive.history(sample_kind='BP排位')[0],2)
        self.assertEqual(self.archive.context(rid)['sample_kind'],'BP排位')
    def test_search_effective_names_literal_wildcards_casefold_and_result_counts(self):
        bid=self.archive.save_battle(self.battle(name='Player%_Quote\'#1234'),'test')
        self.archive.set_perspective(bid,'B');self.archive.set_review(bid,'B')
        self.assertEqual(self.archive.history(query="%_quote'")[0],1)
        self.assertEqual(self.archive.search_results(query='PLAYER')['wins'],1)
        self.archive.set_review(bid,'B',names={'A':'Renamed'})
        self.assertEqual(self.archive.history(query='Player')[0],0)
        self.assertEqual(self.archive.history(query='renamed')[0],1)
        self.assertEqual(self.archive.history(query="' OR 1=1 --")[0],0)
        self.archive.trash_battles([bid]);self.assertEqual(self.archive.history(query='Renamed')[0],0)
        self.archive.restore_last_trash();self.assertEqual(self.archive.history(query='Renamed')[0],1)
    def test_page_reads_bounded_queries_without_loading_original_rosters(self):
        with self.archive.connect() as db:
            for i in range(450):
                b=self.battle(100+i);bid=str(i)
                db.execute('INSERT INTO battles VALUES (?,?,?,?,?,?,?)',(bid,100+i,'saved','test','ready',encode(b),'待选择'))
                self.archive._save_summary(db,bid,b,{'battle_modes':{}})
            # Summaries must serve list/context/statistics without parsing blobs.
            db.execute("UPDATE battles SET original='intentionally unreadable in list tests'")
            statements=[];db.set_trace_callback(statements.append)
            rows=self.archive.contexts([str(i) for i in range(100)],db)
            self.assertEqual(len(rows),100)
            self.assertLess(len([q for q in statements if q.lstrip().upper().startswith('SELECT')]),10)
        total,page=self.archive.history(100,100)
        self.assertEqual(total,450);self.assertEqual(len(page),100)
        self.assertEqual(page[0]['id'],'349');self.assertEqual(page[-1]['id'],'250')
        self.assertEqual(len(self.archive.analysis_dataset()['battles']),450)
    def test_migration_and_light_statistics_match_export_without_rewriting_original(self):
        bid=self.archive.save_battle(self.battle(),'test');self.archive.set_perspective(bid,'A')
        self.archive.set_context(bid,'A','BP排位')
        before=self.archive.get(bid)['original']
        self.assertEqual(analyse(self.archive.analysis_dataset(),load_mappings()),analyse(self.archive.dataset(),load_mappings()))
        with self.archive.connect() as db:db.execute('DELETE FROM battle_summaries')
        reopened=Archive(self.temp.name)
        try:
            self.assertEqual(reopened.history()[0],1)
            self.assertEqual(reopened.get(bid)['original'],before)
        finally:
            for h in reopened.logger.handlers[:]:h.close();reopened.logger.removeHandler(h)


if __name__=='__main__':unittest.main()
