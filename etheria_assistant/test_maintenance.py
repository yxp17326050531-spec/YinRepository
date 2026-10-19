import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analytics import analyse
from legacy_app import App
from base_ui import find_dumpcap
from core import decode_battle,load_mappings
from storage import Archive,project_unit,unit_key
from test_core import battle_body


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.archive=Archive(self.temp.name)

    def tearDown(self):
        for handler in self.archive.logger.handlers[:]:
            handler.close();self.archive.logger.removeHandler(handler)
        self.temp.cleanup()

    def save(self,stamp):
        battle=decode_battle(battle_body(),load_mappings())
        battle['capture_time']=stamp
        return self.archive.save_battle(battle,'test'),battle

    def test_exact_hero_name_mapping_updates_projection_without_changing_skin_or_original(self):
        bid,battle=self.save(100)
        raw=copy.deepcopy(battle['teams']['A'][0]);raw['hero_id']=33151
        untouched=copy.deepcopy(raw)
        self.archive.set_mapping('heroes',33151,'用户确认角色')
        mappings=self.archive.mappings(load_mappings())
        self.assertEqual(project_unit(raw,mappings)['hero_name'],'用户确认角色')
        other=copy.deepcopy(raw);other['hero_id']=33152
        self.assertEqual(project_unit(other,mappings)['hero_name'],'角色 #33152')
        self.assertEqual(raw,untouched)
        self.assertEqual(self.archive.get(bid)['original'],battle)
        with self.archive.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT value FROM mappings WHERE category='heroes' AND id='33151'").fetchone()[0]),'用户确认角色')
        self.archive.remove_mapping('heroes',33151)
        self.assertEqual(project_unit(raw,self.archive.mappings(load_mappings()))['hero_name'],'什炎')

    def test_multiselect_delete_excludes_statistics_related_settlements_and_restores_metadata(self):
        entries=[self.save(100+i) for i in range(3)]
        for bid,battle in entries:
            self.archive.set_context(bid,'A','竞技场','验证组')
            self.archive.set_opponent(bid,'B 队')
            self.archive.save_observation({'kind':'settlement','capture_time':battle['capture_time']+0.5,
                'battle_capture_time':battle['capture_time'],'body_hex':'','winner':'unknown'},'test')
        bid,battle=entries[0]
        key=unit_key('A',0,battle['teams']['A'][0])
        self.archive.annotate(bid,key,'手动智壳',[], '保留备注')
        selected=[entries[0][0],entries[1][0]]
        self.assertEqual(set(self.archive.trash_battles(selected+selected)),set(selected))
        self.assertEqual(self.archive.history()[0],1)
        self.assertEqual(len(self.archive.dataset()['battles']),1)
        self.assertEqual(len(self.archive.validation_dataset()['observations']),1)
        self.assertEqual(len(self.archive.observations('settlement')),1)
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),kinds=('竞技场',))['eligible_matches'],1)
        self.assertEqual(self.archive.get(bid)['original'],battle)
        self.archive.save_battle(battle,'reimport')
        self.assertTrue(self.archive.is_deleted(bid))
        self.assertEqual(self.archive.history()[0],1)
        # A late live status update must not resurrect the deleted record in UI.
        fake=SimpleNamespace(archive=self.archive,live_data='unchanged')
        App.handle_event(fake,'battle',dict(battle,archive_id=bid))
        self.assertEqual(fake.live_data,'unchanged')
        backup=Path(self.temp.name)/'backup.sqlite3';self.archive.backup(backup)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM battle_trash').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM battles').fetchone()[0],3)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(set(self.archive.restore_last_trash()),set(selected))
        self.assertEqual(self.archive.history()[0],3)
        self.assertEqual(len(self.archive.validation_dataset()['observations']),3)
        restored=self.archive.get(bid)
        self.assertEqual(restored['annotations'][key]['note'],'保留备注')
        self.assertEqual(restored['opponent'],'B 队')
        self.assertEqual(self.archive.context(bid)['winner'],'A')

    def test_undo_reverts_only_latest_batch_and_preserves_unlinked_observations(self):
        first,_=self.save(100);second,_=self.save(200)
        self.archive.save_observation({'kind':'settlement','capture_time':101,'battle_capture_time':None,'winner':'unknown'},'test')
        self.archive.trash_battles([first]);self.archive.trash_battles([second])
        self.assertEqual(self.archive.history()[0],0)
        self.assertEqual(len(self.archive.observations('settlement')),1)
        self.assertEqual(self.archive.restore_last_trash(),[second])
        self.assertTrue(self.archive.is_deleted(first))
        self.assertFalse(self.archive.is_deleted(second))
        self.assertEqual(self.archive.restore_last_trash(),[first])
        self.assertEqual(self.archive.restore_last_trash(),[])

    def test_deleted_test_shells_do_not_pollute_candidate_catalogue(self):
        bid,_=self.save(100)
        self.assertTrue(self.archive.shell_catalogue(load_mappings()))
        self.archive.trash_battles([bid])
        self.assertEqual(self.archive.shell_catalogue(load_mappings()),[])
        self.archive.restore_last_trash()
        self.assertTrue(self.archive.shell_catalogue(load_mappings()))

    def test_capture_runtime_search_in_source_and_frozen_layout(self):
        root=Path(self.temp.name)/'app';runtime=root/'vendor'/'dumpcap'/'dumpcap.exe'
        runtime.parent.mkdir(parents=True);runtime.write_bytes(b'placeholder')
        with patch('base_ui.ROOT',root),patch.object(sys,'frozen',False,create=True),patch('base_ui.shutil.which',return_value=None):
            self.assertEqual(find_dumpcap(),str(runtime))
        internal=root/'_internal';internal.mkdir()
        with patch('base_ui.ROOT',internal),patch.object(sys,'executable',str(root/'EtheriaAssistant.exe')),patch.object(sys,'frozen',True,create=True),patch('base_ui.shutil.which',return_value=None):
            self.assertEqual(find_dumpcap(),str(runtime))
        bundled=internal/'vendor'/'dumpcap'/'dumpcap.exe'
        bundled.parent.mkdir(parents=True);bundled.write_bytes(b'placeholder')
        runtime.unlink()
        with patch('base_ui.ROOT',internal),patch.object(sys,'executable',str(root/'EtheriaAssistant.exe')),patch.object(sys,'frozen',True,create=True),patch('base_ui.shutil.which',return_value=None):
            self.assertEqual(find_dumpcap(),str(bundled))


if __name__=='__main__':unittest.main()
