"""Explicit personal replay and outcome reviews never mutate observations."""
import copy
import tempfile
import unittest
from analytics import analyse
from battle_metadata import result_text
from capture import CaptureJob
from core import decode_replay,load_mappings
from storage import Archive
from test_core import battle_body,scalar
from test_replay import replay_body


class Reviews(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name)
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.tmp.cleanup()
    def test_code_382_is_not_unconditionally_a_victory_and_manual_b_win_survives_reimport(self):
        j=CaptureJob(lambda *x:None,20001,load_mappings(),self.archive);j.source='synthetic'
        j.engine.message(0x6003,battle_body(),100);j.engine.message(0x6004,scalar(1,382),110)
        bid=self.archive.history()[1][0]['id'];before=copy.deepcopy(self.archive.get(bid)['original'])
        self.archive.set_perspective(bid,'B');ctx=self.archive.context(bid)
        self.assertEqual(ctx['winner'],'unknown');self.assertEqual(ctx['settlement_candidate'],'A')
        self.assertNotIn('失败',result_text(ctx));self.assertIn('待确认',result_text(ctx))
        self.archive.set_review(bid,'B',names={'A':'SyntheticOpponent','B':'SyntheticLocal'})
        j.engine.message(0x6003,battle_body(),100);j.engine.message(0x6004,scalar(1,382),110)
        ctx=self.archive.context(bid);self.assertEqual(result_text(ctx),'胜利')
        self.assertEqual(ctx['result_origin'],'manual_review');self.assertEqual(ctx['team_names']['B'],'SyntheticLocal')
        self.assertEqual(self.archive.get(bid)['original'],before)
        self.assertEqual(self.archive.dataset()['battles'][0]['winner'],'B')
        self.archive.set_review(bid);self.assertEqual(self.archive.context(bid)['winner'],'unknown')
    def test_personal_replay_requires_explicit_confirmation_side_and_classification(self):
        b=decode_replay(replay_body(),load_mappings());b['capture_time']=100
        bid=self.archive.save_battle(b,'synthetic replay');before=copy.deepcopy(b)
        self.archive.set_classification(bid,'BP排位');self.archive.set_perspective(bid,'B')
        self.assertEqual(self.archive.context(bid)['sample_kind'],'回放/观战')
        self.archive.set_review(bid,'B',True)
        ctx=self.archive.context(bid);self.assertTrue(ctx['personal_confirmed'])
        self.assertEqual(ctx['sample_kind'],'BP排位');self.assertEqual(result_text(ctx),'胜利')
        stats=analyse(self.archive.dataset(),load_mappings(),('BP排位',),perspective='own')
        self.assertEqual(stats['eligible_matches'],1)
        self.archive.set_review(bid,'B',False)
        self.assertEqual(self.archive.context(bid)['sample_kind'],'回放/观战')
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),('BP排位',))['eligible_matches'],0)
        self.assertEqual(self.archive.get(bid)['original'],before)
        self.archive.set_review(bid,'draw',False)
        self.assertEqual(result_text(self.archive.context(bid)),'平局 · 观战，不计本人战绩')
    def test_reimport_can_fill_old_missing_nicknames_without_overwriting_original(self):
        b=decode_replay(replay_body(),load_mappings());b['capture_time']=100;b.pop('participants',None)
        bid=self.archive.save_battle(b,'old');before=copy.deepcopy(b)
        again=copy.deepcopy(b);again['participants']=[{'nickname':'SyntheticOne','team':None},{'nickname':'SyntheticTwo','team':None}]
        self.assertEqual(self.archive.save_battle(again,'new'),bid)
        self.assertEqual(len(self.archive.context(bid)['participants']),2)
        self.assertEqual(self.archive.get(bid)['original'],before)


if __name__=='__main__':unittest.main()
