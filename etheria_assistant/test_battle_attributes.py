"""Synthetic raw-value regression for controlled component/battle comparisons."""
import copy
import tempfile
import unittest
from battle_attributes import pending_attributes, pending_text
from core import Engine, decode_battle, decode_replay, load_mappings
from storage import Archive, project_unit
from capture import CaptureJob
from test_core import scalar, blob, vi


class BattleAttributeTests(unittest.TestCase):
    def roster(self):
        self.raw=[(100000<<8)|1,(20000<<8)|5,(30000<<8)|9,(40000<<8)|13,
                  (0<<8)|171,(1<<63)|(123<<8)|174,(47<<8)|188,(52<<8)|188]
        attrs=b''.join(vi(n) for n in self.raw)
        unit=scalar(1,30153)+blob(4,attrs)
        return blob(2,unit)+blob(3,unit)

    def test_live_and_replay_keep_identical_unknowns_zero_high_bit_and_duplicates(self):
        roster=self.roster();mappings=load_mappings()
        live=decode_battle(blob(1,roster),mappings)
        replay=decode_replay(blob(2,blob(2,roster)),mappings)
        for team in ('A','B'):
            unit=live['teams'][team][0]
            self.assertEqual(unit['attributes_raw'],self.raw)
            self.assertEqual(unit['attributes_raw'],replay['teams'][team][0]['attributes_raw'])
            pending=pending_attributes(unit)
            self.assertEqual([r['tag'] for r in pending],[171,174,188,188])
            self.assertEqual(pending[0]['upper_raw'],0)
            self.assertEqual(pending[1]['raw'],self.raw[5])
            self.assertNotIn('PVP减伤',pending_text(unit))

    def test_live_archive_and_relabel_keep_raw_without_inventory_inference(self):
        roster=self.roster();mappings=load_mappings()
        with tempfile.TemporaryDirectory() as root:
            archive=Archive(root)
            try:
                job=CaptureJob(lambda *args:None,20001,mappings,archive)
                job.engine.message(0x6003,blob(1,roster),100,'synthetic')
                battle=archive.get(archive.history_directory()[0]['id'])['original']
                unit=battle['teams']['B'][0];before=copy.deepcopy(unit)
                self.assertEqual(project_unit(unit,mappings)['attributes_raw'],self.raw)
                self.assertEqual(unit,before)
                self.assertNotIn('components',unit)
            finally:
                for handler in archive.logger.handlers[:]:handler.close();archive.logger.removeHandler(handler)

    def test_old_missing_and_observed_no_unknowns_have_different_messages(self):
        self.assertIsNone(pending_attributes({}))
        self.assertIn('旧记录未保存',pending_text({}))
        self.assertEqual(pending_attributes({'attributes_raw':[(123<<8)|1]}),[])
        self.assertIn('缺失不代表0',pending_text({'attributes_raw':[]}))


if __name__=='__main__':unittest.main()
