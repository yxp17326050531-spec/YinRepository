import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

from core import decode_battle, load_mappings
from storage import Archive, project_unit, unit_key
from capture import CaptureJob
from qt_app import parse_matrices
from test_core import battle_body, pcapng, tcp, frame


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.archive = Archive(self.temp.name)
        self.battle = decode_battle(battle_body(), load_mappings())
        self.battle['capture_time'] = 1700000000.25

    def tearDown(self):
        for handler in self.archive.logger.handlers[:]:
            handler.close()
            self.archive.logger.removeHandler(handler)
        self.temp.cleanup()

    def test_dedup_status_updates_keep_original(self):
        bid = self.archive.save_battle(self.battle, 'import')
        changed = copy.deepcopy(self.battle)
        changed['status'] = 'ended'
        changed['teams']['A'][0]['hero_name'] = 'renamed'
        self.assertEqual(bid, self.archive.save_battle(changed, 'second import'))
        saved = self.archive.get(bid)
        self.assertEqual(saved['original'], self.battle)
        self.assertEqual(saved['status'], 'ended')
        self.assertEqual(self.archive.history()[0], 1)

    def test_manual_scope_and_restore_after_reopen(self):
        bid = self.archive.save_battle(self.battle, 'import')
        key = unit_key('A', 0, self.battle['teams']['A'][0])
        other = copy.deepcopy(self.battle)
        other['capture_time'] += 1
        other_id = self.archive.save_battle(other, 'import')
        matrices = parse_matrices('狂怒,9\n洞悉穿刺，12')
        self.archive.annotate(bid, key, '测试智壳', matrices, '手动核对')
        reopened = Archive(self.temp.name)
        saved = reopened.get(bid)
        self.assertEqual(saved['original'], self.battle)
        self.assertEqual(saved['annotations'][key]['matrices'], matrices)
        self.assertEqual(reopened.get(other_id)['annotations'], {})
        self.assertNotIn(unit_key('B', 0, self.battle['teams']['B'][0]), saved['annotations'])
        self.archive.clear_annotation(bid, key)
        self.assertEqual(self.archive.get(bid)['annotations'], {})

    def test_mapping_projection_does_not_mutate_capture(self):
        self.archive.set_mapping('shell_effects', '38997533', '用户智壳')
        self.archive.set_mapping('matrix_effects', '1171', '用户矩阵', 8)
        mapped = self.archive.mappings(load_mappings())
        original = self.battle['teams']['A'][0]
        before = copy.deepcopy(original)
        rendered = project_unit(original, mapped, {'shell':'手动智壳', 'matrices':[]})
        self.assertEqual(rendered['shells'][0]['name'], '用户智壳')
        self.assertEqual(rendered['manual']['shell'], '手动智壳')
        self.assertEqual(original, before)
        self.archive.remove_mapping('shell_effects', '38997533')
        self.assertEqual(self.archive.mappings(load_mappings())['shell_effects']['38997533']['name'], '伯爵')

    def test_shell_catalogue_dedup_and_user_naming(self):
        battle = copy.deepcopy(self.battle)
        for team in ('A','B'):
            battle['teams'][team][0]['effects_raw'] = [38978531,38978531,83889586,1051]
        self.archive.save_battle(battle, 'capture')
        self.archive.save_battle(battle, 'same capture')
        rows = self.archive.shell_catalogue(load_mappings())
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],38978531)
        self.assertEqual(rows[0]['battle_count'],1)
        self.assertEqual(rows[0]['observations'],2)
        self.assertEqual(rows[0]['name'],'')
        self.archive.set_mapping('shell_effects',38978531,'用户核对名称')
        mapped = self.archive.mappings(load_mappings())
        self.assertEqual(self.archive.shell_catalogue(mapped)[0]['name'],'用户核对名称')
        bid = self.archive.history()[1][0]['id']
        for team in ('A','B'):
            unit = self.archive.get(bid)['original']['teams'][team][0]
            self.assertEqual(project_unit(unit,mapped)['shells'][0]['name'],'用户核对名称')

    def test_invalid_edits_and_sql_backup(self):
        bid = self.archive.save_battle(self.battle, 'import')
        with self.assertRaises(ValueError):
            self.archive.annotate(bid, 'nonexistent', 'name')
        with self.assertRaises(ValueError):
            self.archive.annotate(bid, unit_key('A',0,self.battle['teams']['A'][0]), matrices=[{'name':'狂怒','points':-1}])
        self.archive.save_settings({'interface_id':r'\Device\NPF_{ABCD}', 'port':'20001'})
        destination = str(Path(self.temp.name)/'backup.db')
        self.archive.backup(destination)
        with sqlite3.connect(destination) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM battles').fetchone()[0], 1)
            value = db.execute("SELECT value FROM settings WHERE key='interface_id'").fetchone()[0]
            self.assertEqual(json.loads(value),r'\Device\NPF_{ABCD}')
        self.archive.set_mapping('matrices',3,'用户确认金刚')
        combined=self.archive.mappings(load_mappings())
        self.assertNotIn('3',combined.get('matrix_confidence',{}))
        self.archive.remove_mapping('matrices',3)
        self.assertIn('3',self.archive.mappings(load_mappings())['matrix_confidence'])

    def test_offline_worker_saves_before_ui_event_and_deduplicates(self):
        path = Path(self.temp.name)/'synthetic.pcapng'
        path.write_bytes(pcapng(tcp(frame(0x6003,battle_body()))))
        for _ in range(2):
            events = []
            job = CaptureJob(lambda k,v:events.append((k,v)),20001,load_mappings(),self.archive)
            job.start(path=str(path));job.thread.join(5)
            self.assertFalse(job.thread.is_alive())
            battle = next(v for k,v in events if k=='battle')
            self.assertIsNotNone(self.archive.get(battle['archive_id']))
            self.assertFalse(events[-1][1]['failed'])
        self.assertEqual(self.archive.history()[0],1)

    @unittest.skipIf(os.name=='nt', 'Synthetic executable uses a POSIX shebang')
    def test_live_pipe_stop_and_error_cleanup(self):
        path = Path(self.temp.name)/'fake_dumpcap'
        payload = pcapng(tcp(frame(0x6003,battle_body())))
        path.write_text(f'#!{sys.executable}\nimport sys,time\nsys.stdout.buffer.write({payload!r})\nsys.stdout.buffer.flush()\ntime.sleep(30)\n')
        path.chmod(0o700)
        events=[]
        job=CaptureJob(lambda k,v:events.append((k,v)),20001,load_mappings(),self.archive)
        job.start(dumpcap=str(path),interface='test')
        deadline=time.monotonic()+5
        while not any(k=='battle' for k,v in events) and time.monotonic()<deadline:
            time.sleep(.01)
        try:
            self.assertTrue(any(k=='battle' for k,v in events))
        finally:
            job.stop();job.thread.join(5)
        self.assertFalse(job.thread.is_alive())
        self.assertIsNotNone(job.process.poll())
        self.assertTrue(events[-1][1]['stopped'])
        path.write_text(f'#!{sys.executable}\nimport sys\nprint("synthetic permission error",file=sys.stderr)\nsys.exit(9)\n')
        errors=[]
        job=CaptureJob(lambda k,v:errors.append((k,v)),20001,load_mappings(),self.archive)
        job.start(dumpcap=str(path),interface='test');job.thread.join(5)
        self.assertTrue(any(k=='error' for k,v in errors))
        self.assertTrue(errors[-1][1]['failed'])


if __name__ == '__main__':
    unittest.main()
