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
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPlainTextEdit, QCheckBox, QLabel, QComboBox
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
    def test_confirm_b_side_updates_result_labels_and_keeps_protocol_roster(self):
        self.archive.set_context(self.bid,'A','BP排位')
        original=copy.deepcopy(self.archive.get(self.bid)['original'])
        def edit(d):
            d.findChildren(QComboBox)[0].setCurrentText('B 方是我'); d.commit()
        self.modal(edit);self.window.edit_context(self.bid)
        self.assertIn('失败',self.window.battle_info.text())
        self.assertIn('己方',self.window.team_titles['B'].text())
        self.assertEqual(self.window.team_titles['B'].objectName(),'ownTeam')
        self.assertEqual(self.archive.get(self.bid)['original'],original)
        self.assertEqual(self.window.history_table.item(0,5).text(),'失败')

    def test_history_type_filter_applies_to_navigation_and_return(self):
        self.archive.set_classification(self.bid,'BP排位')
        b=copy.deepcopy(self.battle);b['capture_time']+=1
        arena=self.archive.save_battle(b,'arena');self.archive.set_classification(arena,'竞技场')
        self.window.history_filter.setCurrentText('BP排位')
        self.assertEqual(self.window.history_ids,[self.bid])
        self.window.browse_battle(self.bid)
        self.assertEqual(self.window.battle_jump.count(),1)
        self.window.step_battle(-1);self.assertEqual(self.window.current_id,self.bid)
        self.window.browse_battle(arena);self.window.back_to_history()
        self.assertIsNone(self.window.history_filter.currentData())
        self.assertIn(arena,self.window.selected_ids())

    def test_remember_player_checkbox_and_named_observer_victor(self):
        from capture import CaptureJob
        from test_player_identity import round_start
        from test_core import scalar
        events=[];job=CaptureJob(lambda k,d:events.append((k,d)),20001,load_mappings(),self.archive)
        bid=round_start(job,2000000000)
        job.engine.message(0x6004,scalar(1,383)+scalar(6,17),2000000010,'one')
        self.archive.set_review(bid,'B')
        for kind,data in events:self.window.handle_event(kind,data)
        def edit(d):
            d.findChildren(QComboBox)[0].setCurrentText('B 方是我')
            check=next(c for c in d.findChildren(QCheckBox) if '记住所选玩家' in c.text())
            self.assertTrue(check.isEnabled());check.setChecked(True);d.commit()
        self.modal(edit);self.window.edit_context(bid)
        self.assertIn('胜利',self.window.battle_info.text())
        self.assertTrue(self.archive.settings()['own_player_key'])
        self.archive.set_perspective(bid,None)
        self.archive.save_settings({'own_player_key':'f'*64});self.window.refresh_all()
        self.assertIn('SyntheticTwo',self.window.battle_info.toolTip())
        self.assertIn('己方待确认',self.window.battle_info.toolTip())
        self.archive.set_classification(bid,'回放/观战');self.window.refresh_all()
        self.assertIn('不计本人战绩',self.window.battle_info.toolTip())
        self.assertEqual(self.window.team_titles['B'].text(),'SyntheticTwo')
        self.window.clear_player_identity();self.assertIsNone(self.archive.settings()['own_player_key'])

    def test_eight_characters_and_full_attributes_fit_a_normal_window(self):
        from PySide6.QtCore import QPoint,QRect
        b=copy.deepcopy(self.battle);b['capture_time']+=100
        names=list(load_mappings()['heroes'])[:8]
        for ti,team in enumerate(('A','B')):
            base=b['teams'][team][0];b['teams'][team]=[]
            for i in range(4):
                u=copy.deepcopy(base);u['hero_id']=int(names[ti*4+i])
                u['percent_attributes_tentative']={'crit':77.8,'crit_damage':245.5,'effect_hit':42.1,'effect_resist':15.2}
                u['attributes_raw'] += [(n<<8)|tag for tag,n in [(171,121),(174,187),(41,73),(58,116),(80,63),(83,74)]]
                b['teams'][team].append(u)
        bid=self.archive.save_battle(b,'synthetic eight');self.window.browse_battle(bid);self.window.show()
        for width,height in ((1280,800),(1366,768)):
            self.window.resize(width,height);self.app.processEvents();self.app.processEvents()
            viewport=self.window.battle_scroll.viewport();count=0
            for roster in self.window.team_layouts.values():
                self.assertEqual(roster.count(),4)
                for i in range(roster.count()):
                    card=roster.itemAt(i).widget();rect=QRect(card.mapTo(viewport,QPoint(0,0)),card.size())
                    self.assertTrue(viewport.rect().contains(rect),(width,height,rect));count+=1
                    for metric in card.findChildren(QLabel):
                        if metric.objectName() in ('speed','statValue'):
                            self.assertGreaterEqual(metric.width(),metric.sizeHint().width(),metric.accessibleName())
            self.assertEqual(count,8)
            self.assertEqual(self.window.battle_scroll.horizontalScrollBar().maximum(),0)
            self.assertEqual(self.window.battle_scroll.verticalScrollBar().maximum(),0)
        self.assertFalse(self.window.record_info.isVisible());self.assertFalse(self.window.capture_info.isVisible())

    def test_captured_unassigned_nicknames_can_be_selected_for_team_headers(self):
        b=copy.deepcopy(self.battle);b['capture_time']+=100
        b['participants']=[{'nickname':'SyntheticLeft','team':None},{'nickname':'SyntheticRight','team':None}]
        bid=self.archive.save_battle(b,'synthetic names');before=copy.deepcopy(self.archive.get(bid)['original'])
        self.window.browse_battle(bid);self.window.show();self.app.processEvents()
        self.assertEqual(self.window.team_titles['A'].text(),'记录 A 方')
        self.assertTrue(self.window.nickname_buttons['A'].isVisible())
        def assign(d):
            boxes=d.findChildren(QComboBox);self.assertEqual(boxes[0].currentData(),None)
            boxes[0].setCurrentText('SyntheticRight');boxes[1].setCurrentText('SyntheticLeft');d.commit()
        self.modal(assign);self.window.assign_nicknames()
        self.assertEqual(self.window.team_titles['A'].text(),'SyntheticRight')
        self.assertEqual(self.window.team_titles['B'].text(),'SyntheticLeft')
        self.assertFalse(self.window.nickname_buttons['A'].isVisible())
        self.assertEqual(self.archive.get(bid)['original'],before)

    def test_small_portraits_matrix_colors_and_readable_metrics(self):
        from artwork import portrait,matrix_color
        self.assertFalse(portrait('heroes','瑞玛丽',48).isNull())
        self.assertFalse(portrait('shells','琥珀',32).isNull())
        for name in ('浴血之躯','不屈之誓','荆棘','奋进','时光驾驭','涌泉'):
            self.assertFalse(portrait('matrices',name,24).isNull())
        self.assertEqual(matrix_color('浴血之躯'),'#ff6475');self.assertEqual(matrix_color('不屈之誓'),'#ff6475')
        self.assertEqual(matrix_color('荆棘'),'#ffd34e');self.assertEqual(matrix_color('时光驾驭'),'#6fb8ff')
        self.assertEqual(matrix_color('涌泉'),'#8de56d')
        self.window.show();self.app.processEvents()
        metrics=[w for w in self.window.findChildren(QLabel) if w.objectName()=='statValue']
        self.assertTrue(all(w.font().pixelSize()>=18 for w in metrics))

    def test_review_dialog_sets_b_win_nicknames_and_own_replay_classification(self):
        from core import decode_replay
        from test_replay import replay_body
        b=decode_replay(replay_body(),load_mappings());b['capture_time']=2000000000
        bid=self.archive.save_battle(b,'synthetic replay');self.window.browse_battle(bid)
        def edit(d):
            own=next(c for c in d.findChildren(QCheckBox) if '计入所选分类' in c.text());own.setChecked(True)
            boxes=d.findChildren(QComboBox);boxes[0].setCurrentText('B 方是我');boxes[1].setCurrentText('BP排位');boxes[2].setCurrentText('B 方获胜')
            lines=d.findChildren(QLineEdit);lines[-1].setText('SyntheticLocal');d.commit()
        self.modal(edit);self.window.edit_context(bid)
        self.assertIn('胜利',self.window.battle_info.text());self.assertIn('己方',self.window.team_titles['B'].text())
        self.assertIn('SyntheticLocal',self.window.team_titles['B'].text())
        self.assertEqual(self.archive.context(bid)['sample_kind'],'BP排位')

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
        self.archive.set_perspective(self.bid,'A'); self.archive.set_context(self.bid,'A','竞技场','S1'); self.archive.set_opponent(self.bid,'B 队')
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

    def test_known_replay_response_is_visible_with_automatic_replay_labels(self):
        from capture import CaptureJob
        from test_replay import replay_body
        events=[];job=CaptureJob(lambda k,d:events.append((k,d)),20001,load_mappings(),self.archive)
        job.source='synthetic replay';job.engine.message(0x8421,replay_body(),2000000000)
        job.engine.finish_capture()
        for k,d in events:self.window.handle_event(k,d)
        self.assertEqual(len(self.window.latest['teams']['A']),4)
        self.assertEqual(self.window.team_titles['A'].text(),'记录 A 方')
        self.assertIn('回放阵容已读取',self.window.record_info.text())
        self.assertIn('结果未确认',self.window.battle_info.text())
        self.assertIn('回放 1',self.window.capture_info.text())
        self.assertNotIn('记录不完整',self.window.record_info.text())
        self.window.show();self.app.processEvents()
        values={w.accessibleName():w.text() for w in self.window.findChildren(QLabel) if w.isVisibleTo(self.window.stack.widget(0))}
        self.assertEqual(values['A方 50200 暴击率'],'51.2%')
        self.assertEqual(values['B方 50300 效果抵抗'],'22.2%')

    def test_home_shows_all_attributes_with_zero_missing_and_over_100_percent(self):
        b=copy.deepcopy(self.battle);b['capture_time']+=100
        b['teams']['A'][0]['percent_attributes_tentative']={'crit':0,'crit_damage':423.8,'effect_hit':120.4}
        b['teams']['B'][0].pop('percent_attributes_tentative',None)
        bid=self.archive.save_battle(b,'synthetic attributes')
        self.window.handle_event('battle',dict(b,archive_id=bid))
        self.window.show()
        def shown():
            self.app.processEvents()
            return {w.accessibleName():w.text() for w in self.window.findChildren(QLabel) if w.isVisibleTo(self.window.stack.widget(0))}
        values=shown()
        for title,value in [('生命','28696'),('攻击','4753'),('防御','1883'),('速度','291.00'),
                            ('暴击率','0%'),('暴击伤害','423.8%'),('效果命中','120.4%'),('效果抵抗','—')]:
            self.assertEqual(values['A方 30153 '+title],value)
        for title in ('暴击率','暴击伤害','效果命中','效果抵抗'):
            self.assertEqual(values['B方 30153 '+title],'—')
        self.window.browse_battle(bid)
        self.assertEqual(shown()['A方 30153 暴击伤害'],'423.8%')
        self.assertEqual(self.archive.get(bid)['original'],b)

    def test_fenjin_unknown_threshold_can_be_displayed_and_saved_in_mapping_editor(self):
        from PySide6.QtWidgets import QSpinBox
        b=copy.deepcopy(self.battle);b['teams']['A'][0]['effects_raw']=[1121,33,35]
        bid=self.archive.save_battle(b,'synthetic matrix');self.window.browse_battle(bid)
        self.window.show();self.app.processEvents()
        def displayed():
            self.app.processEvents()
            return [w.text() for w in self.window.findChildren(QLabel) if w.isVisibleTo(self.window.stack.widget(0))]
        self.assertTrue(any('奋进' in t and '?' in t for t in displayed()))
        self.assertTrue(any('档位待确认' in w.toolTip() for w in self.window.findChildren(QLabel) if w.accessibleName()=='矩阵 奋进'))
        self.assertTrue(any('已对照' in w.toolTip() for w in self.window.findChildren(QLabel) if w.accessibleName()=='矩阵 奋进'))
        def save_unknown(d):
            points=d.findChild(QSpinBox);self.assertEqual(points.value(),0)
            self.assertEqual(points.text(),'待确认');d.commit()
        self.modal(save_unknown);self.window.edit_mapping('matrix_effects','1121')
        self.assertIsNone(self.archive.mappings(load_mappings())['matrix_effects']['1121']['threshold'])
        self.assertTrue(any('奋进' in t and '?' in t for t in displayed()))
        self.assertTrue(any('档位待确认' in w.toolTip() for w in self.window.findChildren(QLabel) if w.accessibleName()=='矩阵 奋进'))
        self.assertTrue(any('用户映射' in w.toolTip() for w in self.window.findChildren(QLabel) if w.accessibleName()=='矩阵 奋进'))
        self.assertEqual(self.archive.get(bid)['original'],b)

    def test_component_tab_and_imprint_placeholder_keep_raw_values(self):
        from core import Inventory
        from test_components import component_message
        inventory=Inventory(load_mappings());inventory.update(0x2961,component_message())
        self.window.bag_snapshot=inventory.snapshot(100,[0x2961]);self.window.render_inventory()
        self.assertIn('元件 3 件',self.window.bag_info.text())
        self.window.navigate(2);self.window.inventory_tabs.setCurrentWidget(self.window.component_table)
        self.assertEqual(self.window.component_table.rowCount(),3)
        self.window.component_table.selectRow(1)
        detail=json.loads(self.window.gear_details.toPlainText().split('原始记录：\n',1)[1])
        self.assertEqual(detail['uid'],42);self.assertEqual(detail['field3_raw'],0)
        self.window.gear_query.setText('90003')
        self.assertEqual(self.window.component_table.rowCount(),1)
        self.assertEqual(self.window.component_table.item(0,0).text(),'43')
        b=copy.deepcopy(self.battle);b['teams']['A'][0]['effects_raw'].append(83889586)
        bid=self.archive.save_battle(b,'synthetic imprint');self.window.browse_battle(bid)
        self.window.show();self.app.processEvents()
        self.assertTrue(any('刻影：屠夫' in w.toolTip() for w in self.window.findChildren(QLabel) if w.accessibleName().startswith('矩阵 ')))

    def test_component_projection_search_detail_and_refresh_keeps_original(self):
        raw={'uid':91,'config_id_raw':11048,'field3_raw':3,'field6_raw':1,
             'attributes_raw':[(1240<<16)|(6<<8)|4,(430<<16)|(5<<8)|28]}
        snapshot={'components':[raw], 'component_groups':[{'id_raw':3,'component_uids_raw':[0,0,0,91]}]}
        before=copy.deepcopy(snapshot);self.window.bag_snapshot=snapshot
        self.window.render_inventory();self.window.inventory_tabs.setCurrentWidget(self.window.component_table)
        self.window.gear_query.setText('屠夫');self.assertEqual(self.window.component_table.rowCount(),1)
        self.assertIn('迅影',self.window.component_table.item(0,1).text())
        self.assertEqual(self.window.component_table.item(0,2).text(),'速度 +12.4')
        self.window.component_table.selectRow(0);self.window.render_inventory()
        text=self.window.gear_details.toPlainText()
        self.assertIn('专属加成20%',text);self.assertIn('速度 +14.9',text);self.assertIn('速度 +5.2',text)
        self.assertIn('已锁定',text);self.assertEqual(snapshot,before)
        self.assertEqual(json.loads(text.split('原始记录：\n',1)[1]),raw)
        self.window.gear_query.setText('不存在的元件');self.assertEqual(self.window.component_table.rowCount(),0)

    def test_battle_details_shows_pending_raw_without_claiming_percent_semantics(self):
        unit=copy.deepcopy(self.battle['teams']['B'][0])
        raw=(1<<63)|(123<<8)|188;unit['attributes_raw']=[raw,201]
        def inspect(dialog):
            texts=[w.toPlainText() for w in dialog.findChildren(QPlainTextEdit)]
            pending=next(text for text in texts if '其他属性待对照' in text)
            self.assertIn(str(raw),pending);self.assertIn('#201',pending)
            self.assertNotIn('12.3%',pending)
            original=json.loads(next(text for text in texts if text.startswith('{')))
            self.assertEqual(original['attributes_raw'],[raw,201])
        self.modal(inspect);self.window.details(unit)

    def test_home_and_details_show_both_teams_totals_once_missing_and_zero(self):
        b=copy.deepcopy(self.battle);b['capture_time']+=100
        b['teams']['A'][0]['attributes_raw']=[(121<<8)|171,(1<<63)|(187<<8)|174,
                                            (1<<63)|(73<<8)|41,(116<<8)|58,(88<<8)|179,
                                            (63<<8)|80,(1<<63)|(74<<8)|83]
        b['teams']['B'][0]['attributes_raw']=[171,(1<<63)|(55<<8)|174,83]
        before=copy.deepcopy(b)
        # A local bag must never add its values to transmitted totals or an opponent.
        self.window.bag_snapshot={'components':[{'uid':9,'attributes_raw':[(900<<16)|5]}]}
        bid=self.archive.save_battle(b,'synthetic totals');self.window.browse_battle(bid)
        self.window.show();self.app.processEvents()
        values={w.accessibleName():w for w in self.window.findChildren(QLabel) if w.isVisibleTo(self.window.stack.widget(0))}
        for team,key,value in [('A','PVP增伤','12.1%'),('A','PVP减伤','18.7%'),
                               ('A','额外减伤','7.3%'),('A','无视防御','11.6%'),
                               ('A','结果增伤','6.3%'),('A','结果减伤','7.4%'),
                               ('B','PVP增伤','0%'),('B','PVP减伤','5.5%'),('B','额外减伤','—'),
                               ('B','结果增伤','—'),('B','结果减伤','0%')]:
            self.assertEqual(values[f'{team}方 30153 {key}'].text(),value)
        self.assertIn('对局开场总值',values['A方 30153 PVP增伤'].toolTip())
        # The overview's lower tables must not compress any attribute row.
        self.window.resize(1536,960);self.app.processEvents()
        for name in ('生命','暴击率','PVP增伤','结果增伤'):
            metric=values[f'A方 30153 {name}']
            self.assertGreaterEqual(metric.height(),metric.sizeHint().height())
        def inspect(dialog):
            texts=[w.toPlainText() for w in dialog.findChildren(QPlainTextEdit)]
            totals=next(t for t in texts if '不再次叠加库存' in t)
            self.assertIn('首领增伤：8.8%',totals)
            self.assertIn('PVP减伤：18.7%',totals)
            self.assertIn('伤害结果增伤：6.3%',totals)
            self.assertIn('伤害结果减伤：7.4%',totals)
        self.modal(inspect);self.window.details(self.window.latest['teams']['A'][0])
        self.assertEqual(self.archive.get(bid)['original'],before)
        # Navigating while visible creates children before style polishing.
        # Repeated renders must reserve the styled height, including the frame.
        # Wider glyph spacing reproduces Windows CJK metrics: a wrapping matrix
        # label may prefer two lines in sizeHint(), yet fit on one at its actual
        # layout width. Still reject real clipping at that width.
        base_style=self.window.styleSheet()
        for width,height,spacing in ((1536,960,0),(1050,700,0),(1536,960,7),(1050,700,7),(1536,960,0)):
            self.window.setStyleSheet(base_style+f'\nQLabel#matrixName {{letter-spacing:{spacing}px;}}')
            self.window.resize(width,height);self.window.browse_battle(bid);self.app.processEvents()
            self.app.processEvents()  # Complete nested layout requests after direction changes.
            for metric in self.window.findChildren(QLabel):
                if metric.accessibleName() and metric.isVisibleTo(self.window.stack.widget(0)):
                    required=metric.heightForWidth(metric.width()) if metric.hasHeightForWidth() else metric.sizeHint().height()
                    self.assertGreaterEqual(metric.height(),required,metric.accessibleName())
            for roster in self.window.team_layouts.values():
                cards=[roster.itemAt(i).widget() for i in range(roster.count())]
                for first,second in zip(cards,cards[1:]):
                    self.assertGreaterEqual(second.y(),first.y()+first.height())

if __name__=='__main__':unittest.main()
