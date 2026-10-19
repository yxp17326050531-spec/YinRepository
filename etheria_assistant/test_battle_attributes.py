"""Synthetic raw-value regression for controlled component/battle comparisons."""
import copy
import tempfile
import unittest
from battle_attributes import pending_attributes, pending_text, decode_extra_attributes, extra_text
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
            self.assertEqual([r['tag'] for r in pending],[188,188])
            self.assertEqual(unit['extra_attributes'],{'pvp_damage_bonus':0,'pvp_damage_reduction':12.3})
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

    def test_transmitted_totals_include_baseline_once_and_keep_reduction_positive(self):
        raw=[(63<<8)|171,(1<<63)|(154<<8)|174,(1<<63)|(87<<8)|41,
             (1234<<8)|58,179,(35<<8)|180,(1<<63)|(48<<8)|183,
             (1<<63)|(62<<8)|191,(94<<8)|194,(218<<8)|91]
        before=raw[:];values=decode_extra_attributes(raw)
        self.assertEqual(values,{'pvp_damage_bonus':6.3,'pvp_damage_reduction':15.4,
            'extra_damage_reduction':8.7,'ignore_defense':123.4,'boss_damage_bonus':0,
            'crit_damage_bonus':3.5,'crit_damage_reduction':4.8,'ultimate_damage_reduction':6.2,
            'basic_damage_bonus':9.4,'shield_bonus':21.8})
        self.assertEqual(raw,before)
        self.assertIn('PVP减伤：15.4%',extra_text({'attributes_raw':raw}))
        self.assertIn('不再次叠加库存',extra_text({'attributes_raw':raw}))

    def test_duplicate_known_tags_and_coupled_unknown_fields_are_not_summed(self):
        raw=[(31<<8)|171,(52<<8)|171,(101<<8)|47,(101<<8)|94,174]
        self.assertEqual(decode_extra_attributes(raw),{'pvp_damage_reduction':0})
        self.assertEqual([r['tag'] for r in pending_attributes({'attributes_raw':raw})],[171,171,47,94])
        self.assertEqual(decode_extra_attributes(None),{})

    def test_existing_raw_archives_reproject_without_modifying_original(self):
        unit={'hero_id':30153,'effects_raw':[],'attributes_raw':[(1<<63)|(147<<8)|174],
              'extra_attributes':{'pvp_damage_reduction':999}}
        before=copy.deepcopy(unit)
        display=project_unit(unit,load_mappings())
        self.assertEqual(display['extra_attributes'],{'pvp_damage_reduction':14.7})
        self.assertEqual(unit,before)
        unit.pop('attributes_raw')
        self.assertEqual(project_unit(unit,load_mappings())['extra_attributes'],{})


if __name__=='__main__':unittest.main()
