"""Synthetic ranked results, nickname settings and ambiguous evidence."""
import copy
import json
import tempfile
import unittest
from battle_metadata import result_text
from capture import CaptureJob
from core import load_mappings
from storage import Archive
from test_core import blob, scalar
from test_player_identity import roster


def opening(job, stamp=100, swapped=False, ratings=(3100,3200), names=('First#1234','Second#5678')):
    e=job.engine
    for uid,heroes in ((111111111,(11,12)),(222222222,(21,22))):
        for h in heroes:e.message(0x5fc1,scalar(1,85)+scalar(4,uid)+blob(9,scalar(1,h)),stamp-5,'one')
    profiles=[]
    for uid,name,rating in zip((111111111,222222222),names,ratings):
        profiles.append(blob(8,blob(1,scalar(1,uid)+blob(3,name.encode()))+scalar(2,rating)+scalar(3,22)))
    e.message(0x6001,blob(1,b''.join(reversed(profiles)))+scalar(3,17),stamp-2,'one')
    e.message(0x6003,roster(swapped)+scalar(7,70001),stamp,'one')
    return job.archive.history()[1][0]['id']


def ending(job, before=3100, after=3120, code=382, match_id=70001, marker=17, stamp=110, rank_after=22):
    body=scalar(1,code)+scalar(6,marker)+blob(7,scalar(1,22)+scalar(2,rank_after)+scalar(3,before)+scalar(4,after))+scalar(8,match_id)
    job.engine.message(0x6004,body,stamp,'one')
    return body


class RatingResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name)
        self.job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive);self.job.source='synthetic'
        self.archive.save_settings({'own_nickname':'First'})
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.tmp.cleanup()
    def test_normal_win_and_surrender_loss_follow_player_across_side_swap(self):
        for stamp,swapped,after,code in ((100,True,3120,382),(200,False,3078,381)):
            bid=opening(self.job,stamp,swapped);ending(self.job,after=after,code=code,stamp=stamp+10)
            ctx=self.archive.context(bid)
            self.assertEqual(ctx['own_team'],'B' if swapped else 'A')
            self.assertEqual(ctx['result_origin'],'rating_change')
            self.assertEqual(result_text(ctx),'胜利' if after>3100 else '失败')
            self.assertEqual(ctx['rating_result']['delta'],after-3100)
    def test_result_does_not_depend_on_configured_name_or_code_direction(self):
        bid=opening(self.job,swapped=True);ending(self.job)
        self.archive.save_settings({'own_nickname':'Second#5678'})
        self.assertEqual(result_text(self.archive.context(bid)),'失败')
        self.archive.save_settings({'own_nickname':'Missing'})
        ctx=self.archive.context(bid);self.assertIsNone(ctx['own_team']);self.assertEqual(ctx['winner'],'B')
    def test_same_ratings_unchanged_rating_promotion_missing_or_wrong_ids_stay_unknown(self):
        cases=[({'ratings':(3100,3100)},{}),({}, {'after':3100}),({}, {'rank_after':23}),
               ({},{'match_id':70002}),({},{'marker':18})]
        for i,(start,finish) in enumerate(cases):
            stamp=100+i*100;bid=opening(self.job,stamp,**start);ending(self.job,stamp=stamp+10,**finish)
            self.assertEqual(self.archive.context(bid)['winner'],'unknown',i)
        bid=opening(self.job,800)
        self.job.engine.message(0x6004,scalar(1,382)+scalar(6,17),810,'one')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
    def test_duplicate_opening_and_observer_never_gain_automatic_result(self):
        bid=opening(self.job)
        self.job.engine.message(0x6003,roster()+scalar(7,70001),101,'one');ending(self.job)
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive,'replay')
        bid=opening(job,200);ending(job,stamp=210)
        ctx=self.archive.context(bid);self.assertIsNone(ctx['own_team']);self.assertEqual(ctx['protocol_winner'],'unknown')
    def test_nickname_suffix_duplicate_unbound_and_manual_direction_priority(self):
        bid=opening(self.job,names=('Same#1234','Same#5678'));ending(self.job)
        self.archive.save_settings({'own_nickname':'Same'})
        self.assertIsNone(self.archive.context(bid)['own_team'])
        self.archive.save_settings({'own_nickname':'Same#1234'})
        self.assertEqual(self.archive.context(bid)['own_team'],'A')
        self.archive.set_perspective(bid,'B');self.assertEqual(self.archive.context(bid)['own_team'],'B')
        self.archive.set_perspective(bid,None)
        with self.archive.connect() as db:
            players=json.loads(db.execute('SELECT value FROM battle_players WHERE battle_id=?',(bid,)).fetchone()[0])
        for p in players:p['team']=None
        # No preview/profile-order shortcut when a name has no confirmed side.
        with self.archive.connect() as db:db.execute('UPDATE battle_players SET value=? WHERE battle_id=?',(json.dumps(players),bid))
        self.assertIsNone(self.archive.context(bid)['own_team'])
    def test_manual_result_and_clear_settings_reproject_without_changing_original(self):
        bid=opening(self.job);ending(self.job)
        original=copy.deepcopy(self.archive.get(bid)['original'])
        self.archive.set_review(bid,'B');self.assertEqual(result_text(self.archive.context(bid)),'失败')
        self.archive.set_review(bid,None);self.assertEqual(result_text(self.archive.context(bid)),'胜利')
        self.archive.save_settings({'own_nickname':''})
        self.assertIsNone(self.archive.context(bid)['own_team'])
        self.assertEqual(self.archive.get(bid)['original'],original)
    def test_conflicting_settlement_is_sticky_unknown_and_reimport_is_idempotent(self):
        bid=opening(self.job);body=ending(self.job)
        observation={'kind':'settlement','capture_time':110,'battle_capture_time':100,'battle_record_id':bid,
                     'connection_id':'one','association_status':'linked','body_hex':body.hex()}
        self.archive.save_observation(observation,'synthetic')
        self.assertEqual(self.archive.context(bid)['winner'],'A')
        conflicting=scalar(1,381)+scalar(6,17)+blob(7,scalar(1,22)+scalar(2,22)+scalar(3,3100)+scalar(4,3080))+scalar(8,70001)
        observation['body_hex']=conflicting.hex();self.archive.save_observation(observation,'synthetic')
        observation['body_hex']=body.hex();self.archive.save_observation(observation,'synthetic')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')

    def test_reimport_enriches_old_record_and_restart_preserves_projection(self):
        bid=opening(self.job);ending(self.job)
        original=self.archive.get(bid)['original']
        # Emulate an old archive with no opening/score projection. Reimport
        # enriches separate tables while preserving its original observations.
        with self.archive.connect() as db:
            db.execute('DELETE FROM rating_openings');db.execute('DELETE FROM rating_results')
        fresh=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive)
        self.assertEqual(opening(fresh),bid);ending(fresh)
        self.assertEqual(self.archive.get(bid)['original'],original)
        reopened=Archive(self.tmp.name)
        try:self.assertEqual(result_text(reopened.context(bid)),'胜利')
        finally:
            for h in reopened.logger.handlers[:]:h.close();reopened.logger.removeHandler(h)


if __name__=='__main__':unittest.main()
