"""Synthetic identity and observer outcome regressions; no user captures."""
import copy
import hashlib
import json
import tempfile
import unittest
from analytics import analyse
from battle_metadata import result_text
from capture import CaptureJob
from core import load_mappings, record
from storage import Archive
from test_core import blob, scalar, vi


def roster(swapped=False, marker=17):
    attrs=b''.join(vi((n*100)<<8|tag) for tag,n in [(1,20000),(5,3000),(9,2000),(13,300)])
    teams=[range(11,15),range(21,25)]
    if swapped:teams.reverse()
    return blob(1,b''.join(blob(group,scalar(1,h)+blob(4,attrs)+blob(6,vi(38997533)))
        for group,heroes in zip((2,3),teams) for h in heroes))+scalar(5,marker)


def player_header(reverse=False, name='SyntheticOne'):
    players=[(111111111,name),(222222222,'SyntheticTwo')]
    if reverse:players.reverse()
    return blob(1,b''.join(blob(8,blob(1,scalar(1,uid)+blob(3,nick.encode()))) for uid,nick in players))+scalar(3,17)


def round_start(job, stamp=100, swapped=False, connection='one', name='SyntheticOne', preview=False):
    e=job.engine
    for uid,heroes in [(111111111,(11,12)),(222222222,(21,22))]:
        for i,h in enumerate(heroes):
            e.message(0x5fc1,scalar(1,84 if preview else 85)+scalar(4,uid)+blob(9,scalar(1,h)),stamp-8+i,connection)
    e.message(0x6001,player_header(reverse=swapped,name=name),stamp-3,connection)
    e.message(0x6003,roster(swapped),stamp,connection)
    return job.archive.history()[1][0]['id'] if job.archive else None


class PlayerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name);self.events=[]
        self.job=CaptureJob(lambda k,d:self.events.append((k,d)),20001,load_mappings(),self.archive);self.job.source='synthetic'
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.tmp.cleanup()
    def settle(self, job=None, code=382, stamp=110, marker=17, connection='one'):
        (job or self.job).engine.message(0x6004,scalar(1,code)+scalar(6,marker),stamp,connection)
    def test_remembered_player_survives_side_swap_profile_order_and_nickname_change(self):
        first=round_start(self.job);self.settle()
        self.archive.set_perspective(first,'A',remember=True)
        second=round_start(self.job,200,swapped=True,name='RenamedPlayer');self.settle(stamp=210)
        self.archive.set_review(second,'A')
        ctx=self.archive.context(second)
        self.assertEqual(ctx['own_team'],'B');self.assertEqual(ctx['side_origin'],'player_identity')
        self.assertEqual(result_text(ctx),'失败');self.assertEqual(ctx['team_names']['B'],'RenamedPlayer')
        self.archive.save_settings({'own_player_key':None})
        self.assertNotEqual(self.archive.context(second)['side_origin'],'player_identity')
    def test_private_keys_and_account_ids_never_enter_original_ui_or_exports(self):
        bid=round_start(self.job);self.settle();self.archive.set_perspective(bid,'A',remember=True)
        key=self.archive.settings()['own_player_key']
        text=json.dumps([self.archive.get(bid),self.archive.context(bid),self.archive.dataset(),
                         self.job.engine.diagnostics(),self.events])
        self.assertNotIn(key,text);self.assertNotIn('player_key',text)
        self.assertNotIn('111111111',text);self.assertNotIn('222222222',text)
        self.assertNotIn('_local_players',text)
    def test_known_local_player_absent_never_becomes_personal_loss_or_guessed_mode(self):
        bid=round_start(self.job);self.settle(code=383)
        self.archive.set_review(bid,'B')
        self.archive.save_settings({'own_player_key':hashlib.sha256(b'different synthetic player').hexdigest()})
        ctx=self.archive.context(bid)
        self.assertEqual(ctx['sample_kind'],'未分类');self.assertIsNone(ctx['own_team'])
        self.assertEqual(ctx['protocol_winner'],'B');self.assertIn('SyntheticTwo',result_text(ctx))
        self.assertIn('己方待确认',result_text(ctx))
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),('未分类',),perspective='own')['eligible_matches'],0)
    def test_explicit_observer_retains_protocol_victor_without_personal_result(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive,'replay')
        bid=round_start(job);self.settle(job,383)
        self.archive.set_review(bid,'B')
        ctx=self.archive.context(bid)
        self.assertEqual(ctx['winner'],'unknown');self.assertEqual(ctx['protocol_winner'],'B')
        self.assertIn('SyntheticTwo',result_text(ctx))
        self.assertEqual(self.archive.get(bid)['tracking']['state'],'settled')
    def test_preview_or_missing_draft_never_binds_profile_order(self):
        bid=round_start(self.job,preview=True)
        ctx=self.archive.context(bid);self.assertEqual(ctx['team_names'],{})
        self.assertIsNone(ctx['own_team'])
        with self.assertRaises(ValueError):self.archive.set_perspective(bid,'A',remember=True)
        self.assertIsNone(self.archive.context(bid)['own_team'])
    def test_identity_does_not_cross_connection_or_survive_stale_header(self):
        e=self.job.engine
        for h in (11,12):e.message(0x5fc1,scalar(1,85)+scalar(4,111111111)+blob(9,scalar(1,h)),90,'one')
        e.message(0x6001,player_header(),91,'one');e.message(0x6003,roster(),100,'two')
        bid=self.archive.history()[1][0]['id'];self.assertEqual(self.archive.context(bid)['participants'],[])
        e.message(0x6003,roster(),200,'one')
        bid=self.archive.history()[1][0]['id'];self.assertEqual(self.archive.context(bid)['participants'],[])
    def test_context_marker_mismatch_and_wrong_connection_are_rejected(self):
        bid=round_start(self.job);self.settle(marker=18)
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        self.assertIn('编号不一致',self.archive.get(bid)['status'])
        observation={'kind':'settlement','capture_time':111,'battle_capture_time':100,
            'battle_record_id':bid,'body_hex':(scalar(1,382)+scalar(6,17)).hex(),'connection_id':'other'}
        self.archive.save_observation(observation,'synthetic')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        observation['connection_id']='one';observation['body_hex']=(scalar(1,382)+scalar(6,18)).hex()
        self.archive.save_observation(observation,'synthetic');self.assertEqual(self.archive.context(bid)['winner'],'unknown')
    def test_observer_duplicate_opening_cannot_gain_a_winner(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive,'replay')
        bid=round_start(job);job.engine.message(0x6003,roster(),101,'one');self.settle(job,383)
        self.assertEqual(self.archive.context(bid)['protocol_winner'],'unknown')
    def test_conflicting_player_directions_stay_unknown(self):
        bid=round_start(self.job)
        with self.archive.connect() as db:players=json.loads(db.execute('SELECT value FROM battle_players').fetchone()[0])
        conflict=copy.deepcopy(players)
        for p in conflict:p['team']='B' if p['team']=='A' else 'A'
        self.archive.save_players(bid,conflict);self.archive.save_players(bid,players)
        self.assertEqual(self.archive.context(bid)['team_names'],{})


if __name__=='__main__':unittest.main()
