"""Automatic outcome persistence, association and old-observation replay."""
import tempfile
import unittest
from capture import CaptureJob
from core import decode_battle, load_mappings
from storage import Archive
from test_core import battle_body, scalar

class AutomaticResults(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.archive=Archive(self.tmp.name)
        self.job=CaptureJob(lambda *args:None,20001,load_mappings(),self.archive); self.job.source='test'
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.tmp.cleanup()
    def test_two_results_export_and_classification(self):
        for stamp,code,winner in [(100,382,'A'),(200,383,'B')]:
            self.job.engine.message(0x6003,battle_body(),stamp)
            self.job.engine.message(0x6004,scalar(1,code),stamp+10)
            bid=self.archive.history()[1][0]['id']; self.archive.set_classification(bid,'竞技场','S1')
            self.assertEqual(self.archive.context(bid)['winner'],winner)
        ds=self.archive.dataset();self.assertEqual([b['winner'] for b in ds['battles']],['A','B'])
        self.assertTrue(all(b['result_origin']=='automatic' for b in ds['battles']))
    def test_unlinked_duplicate_unknown_and_conflict(self):
        self.job.engine.message(0x6004,scalar(1,382),90)
        self.job.engine.message(0x6003,battle_body(),100)
        bid=self.archive.history()[1][0]['id']
        self.job.engine.message(0x6004,scalar(1,999),110)
        self.job.engine.message(0x6004,scalar(1,382),120)
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        data={'kind':'settlement','capture_time':111,'battle_capture_time':100,'body_hex':scalar(1,383).hex()}
        self.archive.save_observation(data,'different source');self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        self.archive.save_observation(data,'test');self.assertEqual(self.archive.context(bid)['winner'],'B')
        data['body_hex']=scalar(1,382).hex();self.archive.save_observation(data,'test')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
    def test_replay_old_observation_and_deleted_record(self):
        battle=decode_battle(battle_body(),load_mappings());battle['capture_time']=100
        bid=self.archive.save_battle(battle,'test')
        self.archive.save_observation({'kind':'settlement','capture_time':110,'battle_capture_time':100,'body_hex':scalar(1,382).hex()},'test')
        with self.archive.connect() as db:db.execute('DELETE FROM automatic_results')
        reopened=Archive(self.tmp.name);self.assertEqual(reopened.context(bid)['winner'],'A')
        reopened.trash_battles([bid]);self.assertEqual(reopened.dataset()['battles'],[])
