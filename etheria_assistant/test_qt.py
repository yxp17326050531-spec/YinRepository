"""Offscreen integration tests for real Qt widgets and persistence."""
import copy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPlainTextEdit, QCheckBox
from qt_app import MainWindow, Editor
from core import decode_battle, load_mappings
from storage import Archive
from test_core import battle_body, pcapng, tcp, frame
from equipment import normalize_filters
from test_equipment import gear, attr

class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.archive=Archive(self.temp.name)
        self.window=MainWindow(self.archive); self.window.navigate(0)
        self.battle=decode_battle(battle_body(),load_mappings()); self.battle['capture_time']=1700000000.25
        self.bid=self.archive.save_battle(self.battle,'Qt test'); self.window.current_id=self.bid; self.window.live_id=self.bid
        self.window.refresh_all(); self.app.processEvents()
    def tearDown(self):
        self.window.close(); self.app.processEvents()
        for h in self.archive.logger.handlers[:]:h.close(); self.archive.logger.removeHandler(h)
        self.temp.cleanup()
    def modal(self,operation):
        def run():
            d=QApplication.activeModalWidget()
            self.assertIsInstance(d,Editor)
            try:operation(d)
            finally:
                if d.isVisible():d.reject()
        QTimer.singleShot(0,run)
    def test_exact_name_save_and_scoped_manual_loadout(self):
        u=self.window.latest['teams']['A'][0]; hid=u['hero_id']; original=copy.deepcopy(self.battle)
        self.modal(lambda d:(d.findChild(QLineEdit).setText('我的皮肤名称'),d.commit()))
        self.window.edit_hero(u)
        self.assertEqual(self.window.latest['teams']['A'][0]['hero_name'],'我的皮肤名称')
        self.assertEqual(self.archive.get(self.bid)['original'],original)
        def edit(d):
            d.findChild(QLineEdit).setText('伯爵')
            checks=d.findChildren(QCheckBox); checks[0].setChecked(True)
            d.findChildren(QPlainTextEdit)[0].setPlainText('狂怒,9\n洞悉穿刺,12'); d.commit()
        self.modal(edit); self.window.edit_loadout(self.window.latest['teams']['A'][0])
        annotation=list(self.archive.get(self.bid)['annotations'].values())[0]
        self.assertEqual(annotation['shell'],'伯爵'); self.assertEqual(annotation['matrices'][0]['points'],9)
        self.assertEqual(self.archive.get(self.bid)['original'],original)
    def test_multiselect_delete_restore_and_late_event(self):
        b=copy.deepcopy(self.battle); b['capture_time']+=1; second=self.archive.save_battle(b,'second')
        self.window.refresh_history(); self.window.history_table.selectAll(); self.window.delete_history()
        self.assertEqual(self.archive.history()[0],0); self.assertIsNone(self.window.latest)
        self.window.handle_event('battle',dict(self.battle,archive_id=self.bid)); self.assertIsNone(self.window.latest)
        self.window.restore_history(); self.assertEqual(self.archive.history()[0],2)
        self.assertFalse(self.archive.is_deleted(second))
    def test_worker_import_and_navigation_from_saved_archive(self):
        path=os.path.join(self.temp.name,'sample.pcapng')
        # Use the same packet fixtures as the parser regression tests.
        with open(path,'wb') as f:f.write(pcapng(tcp(frame(0x6003,battle_body()),1000)))
        self.window.start_job(path=path)
        deadline=time.monotonic()+4
        while (self.window.job.thread.is_alive() or not self.window.events.empty()) and time.monotonic()<deadline:
            self.app.processEvents(); self.window.poll(); time.sleep(.01)
        self.assertFalse(self.window.job.thread.is_alive()); self.assertTrue(self.window.start_btn.isEnabled())
        self.assertIsNotNone(self.window.current_id)
        for i in range(6):self.window.navigate(i); self.app.processEvents(); self.assertEqual(self.window.stack.currentIndex(),i)
    def test_storage_failure_keeps_current_exportable_and_warning(self):
        self.window.current_id=None
        self.window.handle_event('storage_error','disk full')
        self.window.handle_event('battle',self.battle)
        self.assertEqual(self.window.latest['teams'],self.battle['teams'])
        self.window.handle_event('done',{'failed':False})
        self.assertIn('自动保存发生错误',self.window.statusBar().currentMessage())
        self.assertIsNotNone(self.window.latest)

    def test_skin_name_is_not_merged_and_stats_respect_context(self):
        self.archive.set_context(self.bid,'A','竞技场','S1'); self.archive.set_opponent(self.bid,'B 队')
        self.window.stats_kind.setCurrentText('竞技场'); self.window.stats_min.setValue(1); self.window.refresh_stats()
        self.assertGreater(self.window.stat_tables[0].rowCount(),0)
        self.window.stats_group.setText('other'); self.window.refresh_stats(); self.assertEqual(self.window.stat_tables[0].rowCount(),0)
        self.archive.set_mapping('heroes',32101,'斐莫莉安'); self.window.mapping_changed()
        self.assertEqual(self.window.hero_name(32101),'斐莫莉安'); self.assertEqual(self.window.hero_name(32102),load_mappings()['heroes'].get('32102','角色 #32102'))

    def test_equipment_filter_dialog_persistence_and_live_selection(self):
        self.window.bag_snapshot={'gear':[gear(),gear(43,matrix=15)],'capture_time':100}
        self.window.render_inventory(); self.window.navigate(2)
        self.assertEqual(self.window.gear_table.rowCount(),2)
        from inventory_widgets import GearFilterDialog
        def choose():
            d=QApplication.activeModalWidget(); self.assertIsInstance(d,GearFilterDialog)
            d.choices['matrix']['1'].setChecked(True)
            d.choices['subs']['16'].setChecked(True); d.choices['subs']['22'].setChecked(True); d.accept()
        QTimer.singleShot(0,choose); self.window.edit_gear_filters()
        self.assertEqual(self.window.gear_table.rowCount(),1)
        self.assertEqual(self.archive.settings()['gear_filters']['matrix'],['1'])
        self.window.gear_table.selectRow(0)
        changed=gear(level=6,attrs=[attr(8,15000),attr(22,64,1),attr(16,570,1)])
        self.window.handle_event('inventory_snapshot',{'gear':[gear(43,matrix=15),changed],'capture_time':101})
        self.assertEqual(self.window.gear_display[self.window.gear_table.currentRow()]['uid'],42)
        self.assertIn('速度 +5.7',self.window.gear_details.toPlainText())
        self.window.gear_filters=normalize_filters({'subs':['16','25']}); self.window.render_inventory()
        self.assertEqual(self.window.gear_table.rowCount(),0)
        self.window.clear_gear_filters(); self.assertEqual(self.window.gear_table.rowCount(),2)

    def test_equipment_metadata_editor_does_not_modify_raw_snapshot(self):
        original=gear(); self.window.bag_snapshot={'gear':[original],'capture_time':100}
        self.window.render_inventory(); self.window.gear_table.selectRow(0)
        from PySide6.QtWidgets import QComboBox
        def edit(d):
            boxes=d.findChildren(QComboBox); boxes[0].setCurrentText('超凡'); boxes[1].setCurrentText('3'); d.commit()
        self.modal(edit); self.window.edit_gear_metadata()
        self.assertEqual(self.archive.gear_metadata()[42],{'rarity':'超凡','initial_sub_count':3})
        self.assertEqual(self.window.bag_snapshot['gear'][0],original)

    def test_attribute_sort_controls_persist_and_retain_selected_uid(self):
        bag=[gear(1,attrs=[attr(8,33000),attr(16,1560)]),
             gear(2,attrs=[attr(8,33000),attr(16,1620)]),
             gear(3,attrs=[attr(8,33000)]),
             gear(4,attrs=[attr(8,33000),attr(16,1590)])]
        self.window.bag_snapshot={'gear':bag,'capture_time':100};self.window.render_inventory()
        self.window.gear_table.selectRow(0)
        control=self.window.gear_sort_key;control.setCurrentIndex(control.findData('attr:16'))
        self.assertEqual([g['uid'] for g in self.window.gear_display],[2,4,1,3])
        self.assertEqual(self.window.gear_display[self.window.gear_table.currentRow()]['uid'],1)
        self.assertEqual(self.window.gear_table.item(0,2).text(),'16.2')
        self.window.gear_sort_order.setCurrentText('从低到高')
        self.assertEqual([g['uid'] for g in self.window.gear_display],[1,4,2,3])
        self.assertEqual(self.archive.settings()['gear_sort'],{'key':'attr:16','scope':'subs','descending':False})
        fresh=MainWindow(self.archive)
        self.assertEqual(fresh.gear_sort,self.window.gear_sort);fresh.close()
        self.window.gear_filters=normalize_filters({'subs':['16']});self.window.render_inventory()
        self.assertEqual([g['uid'] for g in self.window.gear_display],[1,4,2])

    def test_continuous_history_navigation_skips_deleted_and_live_does_not_interrupt(self):
        ids=[]
        for i in range(4):
            b=copy.deepcopy(self.battle);b['capture_time']+=i+1;ids.append(self.archive.save_battle(b,'navigation'))
        self.archive.trash_battles([ids[1]])
        self.window.browse_battle(ids[0]);self.window.step_battle(-1)
        self.assertEqual(self.window.current_id,ids[2])
        self.window.step_battle(1);self.assertEqual(self.window.current_id,ids[0])
        index=self.window.battle_jump.findData(ids[3]);self.window.battle_jump.setCurrentIndex(index)
        self.assertEqual(self.window.current_id,ids[3])
        self.assertFalse(self.window.next_battle.isEnabled())
        newer=copy.deepcopy(self.battle);newer['capture_time']+=20;newid=self.archive.save_battle(newer,'live')
        self.window.handle_event('battle',dict(newer,archive_id=newid))
        self.assertEqual(self.window.current_id,ids[3]);self.assertEqual(self.window.live_id,newid)
        self.assertGreaterEqual(self.window.battle_jump.findData(newid),0)
        self.assertTrue(self.window.next_battle.isEnabled())
        self.window.return_live();self.assertEqual(self.window.current_id,newid)
        self.window.step_battle(1);self.assertEqual(self.window.current_id,ids[3])
        self.window.back_to_history();self.assertEqual(self.window.stack.currentIndex(),3)
        self.assertIn(ids[3],self.window.selected_ids())

    def test_navigation_crosses_history_page_boundary(self):
        ids=[]
        for i in range(103):
            b=copy.deepcopy(self.battle);b['capture_time']+=i+1;ids.append(self.archive.save_battle(b,'pages'))
        self.window.browse_battle(ids[1]);self.window.step_battle(1)
        self.assertEqual(self.window.current_id,ids[0]);self.window.back_to_history()
        self.assertEqual(self.window.history_offset,100);self.assertIn(ids[0],self.window.selected_ids())

    def test_replay_capture_diagnostics_and_old_connection_event(self):
        from capture import CaptureJob
        events=[];job=CaptureJob(lambda k,d:events.append((k,d)),20001,load_mappings(),self.archive,'replay');job.source='replay'
        job.engine.message(0x6003,battle_body(),2000000000)
        for k,d in events:self.window.handle_event(k,d)
        self.assertEqual(self.window.team_titles['A'].text(),'记录 A 方')
        self.assertIn('不计本人战绩',self.window.record_info.text())
        replay_id=self.window.current_id
        old=copy.deepcopy(self.battle);old['capture_time']=100;oldid=self.archive.save_battle(old,'old')
        self.window.handle_event('battle',dict(old,archive_id=oldid))
        self.assertEqual(self.window.live_id,replay_id)
        self.window.render_capture_diagnostics({'capture_context':'replay','counts':{'game_packets':10,'framing_discarded_bytes':20}})
        self.assertIn('消息边界未同步',self.window.capture_info.text())

if __name__=='__main__':unittest.main()
