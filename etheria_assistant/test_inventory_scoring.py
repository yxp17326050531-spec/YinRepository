"""Synthetic rule, sharing, rollback and native inventory integration regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import load_mappings
from gear_scoring import default_rules,validate_rules,score_gear,score_text,rounded_speed
from mapping_presets import MappingPresets,validate_bundle,read_bundle
from storage import Archive
from test_equipment import gear,attr


def item(speed=1800,matrix=4,points=3,uid=1,count=0):
    return gear(uid=uid,level=15,matrix=matrix,points=points,
                attrs=[attr(8,33000),attr(16,speed,count),attr(3,100),attr(11,100),attr(25,100)])


def close_archive(archive):
    for h in archive.logger.handlers[:]:h.close();archive.logger.removeHandler(h)


class ScoringRulesTests(unittest.TestCase):
    def setUp(self):self.rules=default_rules();self.maps=load_mappings()
    def speed_score(self,g):return next(r for r in score_gear(g,self.maps,self.rules)['roles'] if r['key']=='speed')
    def test_default_rules_validate_and_maxima_are_reference_not_caps(self):
        self.assertEqual(validate_rules(self.rules),self.rules)
        self.assertGreater(self.speed_score(item(2100))['score'],self.speed_score(item(1950))['score'])
        self.assertEqual(rounded_speed(19.5),20);self.assertEqual(rounded_speed(18.5),19)
    def test_exact_speed_sorting_and_cross_matrix_preference(self):
        self.assertGreater(self.speed_score(item(1800))['score'],self.speed_score(item(1900,matrix=1))['score'])
        self.assertGreater(self.speed_score(item(1920))['score'],self.speed_score(item(1890))['score'])
        self.assertGreater(self.speed_score(item(1950))['score']-self.speed_score(item(1850))['score'],
                           self.speed_score(item(1850))['score']-self.speed_score(item(1750))['score'])
    def test_speed_is_independent_of_raw_upgrade_count_and_manual_metadata(self):
        a=item(1450,count=0);b=item(1450,count=5)
        self.assertEqual(self.speed_score(a)['score'],self.speed_score(b)['score'])
        self.assertTrue(self.speed_score(a)['eligible'])
        self.assertEqual(score_gear(a,self.maps,self.rules,{'speed_upgrade_count_confirmed':5}),score_gear(a,self.maps,self.rules))
    def test_all_twelve_confirmed_eight_piece_matrices_ignore_two_point_discount(self):
        self.assertEqual(len(self.rules['speed']['eight_piece']),12)
        reverse={v:int(k) for k,v in self.maps['matrices'].items()}
        for name in self.rules['speed']['eight_piece']:
            self.assertEqual(self.speed_score(item(matrix=reverse[name],points=2))['score'],
                             self.speed_score(item(matrix=reverse[name],points=3))['score'],name)
        self.assertAlmostEqual(self.speed_score(item(matrix=64,points=2))['score']/self.speed_score(item(matrix=64,points=3))['score'],0.7)
        self.assertAlmostEqual(self.speed_score(item(matrix=12))['matrix_factor'],0.7)
    def test_point_discount_also_applies_to_non_speed_roles(self):
        def role(g):return next(r for r in score_gear(g,self.maps,self.rules)['roles'] if r['key']=='survival')['score']
        self.assertAlmostEqual(role(item(matrix=64,points=2))/role(item(matrix=64,points=3)),0.7)
        self.assertEqual(role(item(matrix=12,points=2)),role(item(matrix=12,points=3)))
    def test_fixed_values_equal_percentages_without_extra_half_discount(self):
        fixed=gear(attrs=[attr(8,33000),attr(4,60000),attr(8,6000),attr(12,4000),attr(16,1500)])
        percent=gear(attrs=[attr(8,33000),attr(3,40),attr(7,40),attr(11,40),attr(16,1500)])
        a=score_gear(fixed,self.maps,self.rules);b=score_gear(percent,self.maps,self.rules)
        for left,right in zip(a['roles'],b['roles']):self.assertEqual(left['score'],right['score'])
        self.assertIn('等效4%',score_text(a,self.rules))
    def test_multi_role_scores_detail_excludes_ineffective_attributes_and_main(self):
        g=item();before=copy.deepcopy(g);r=score_gear(g,self.maps,self.rules)
        rows={x['key']:x for x in r['roles']}
        self.assertTrue(rows['accuracy']['eligible']);self.assertTrue(rows['survival']['eligible'])
        self.assertFalse(rows['attack']['eligible'])
        self.assertFalse(next(a for a in rows['survival']['contributions'] if a['name']=='效果命中')['used'])
        self.assertEqual(g,before)
        self.assertEqual(r['score'],max(x['score'] for x in r['roles'] if x['eligible']))
    def test_unknown_attribute_prevents_final_scoring_and_unknown_matrix_prevents_speed_score(self):
        g=item();g['attributes_raw'].append(attr(111,100))
        r=score_gear(g,self.maps,self.rules);self.assertFalse(r['complete']);self.assertIsNone(r['score'])
        g=item(matrix=9999);self.assertIsNone(self.speed_score(g)['score'])
        g=item(points=1);self.assertIsNone(self.speed_score(g)['score'])
    def test_threshold_and_import_validation(self):
        self.assertFalse(self.speed_score(item(1300))['eligible'])
        for mutation in (lambda r:r['references'].update({'3':0}),lambda r:r['speed'].update({'curve':[[19,200],[18,300]]}),
                         lambda r:r.update({'minimum_score':float('nan')}),lambda r:r['speed'].update({'two_points_factor':-1})):
            bad=copy.deepcopy(self.rules);mutation(bad)
            with self.assertRaises(ValueError):validate_rules(bad)


class MappingPresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name);self.store=MappingPresets(self.archive)
    def tearDown(self):close_archive(self.archive);self.tmp.cleanup()
    def bundle(self,rows):return {'format':'etheria-mapping-preset','schema':1,'name':'测试映射','mappings':rows}
    def test_export_contains_only_custom_mapping_and_roundtrips_utf8(self):
        self.archive.set_mapping('heroes',9991,'测试角色');self.archive.set_mapping('matrix_effects',9992,'测试矩阵',8)
        self.archive.save_settings({'own_nickname':'private-name'})
        b=self.store.snapshot('我的编号');self.assertEqual(set(b['mappings']),{'heroes','matrix_effects'})
        self.assertNotIn('private-name',json.dumps(b,ensure_ascii=False))
        p=Path(self.tmp.name)/'preset.json';p.write_text(json.dumps(b,ensure_ascii=False),encoding='utf-8')
        self.assertEqual(read_bundle(p),b);self.store.save(b)
        self.assertEqual(MappingPresets(self.archive).presets()[b['name']],b)
        self.store.delete(b['name']);self.assertEqual(self.store.presets(),{})
        self.assertEqual(self.archive.custom_mappings('heroes')['9991'],'测试角色')
    def test_conflict_default_keep_and_explicit_overwrite_with_persistent_undo(self):
        self.archive.set_mapping('heroes',9991,'本地')
        b=self.bundle({'heroes':{'9991':'分享','9992':'新增'}})
        self.assertEqual(self.store.preview(b,load_mappings())['conflict'],1)
        self.assertEqual(self.store.apply(b),1);self.assertEqual(self.archive.custom_mappings('heroes')['9991'],'本地')
        self.assertEqual(self.store.undo(),(1,0));self.assertEqual(self.store.apply(b,True),2)
        self.assertEqual(MappingPresets(self.archive).undo(),(2,0))
        self.assertEqual(self.archive.custom_mappings('heroes'),{'9991':'本地'})
    def test_undo_skips_later_edits_and_builtin_is_restored(self):
        self.store.apply(self.bundle({'matrices':{'4':'分享疾驰'},'heroes':{'9991':'分享'}}))
        self.archive.set_mapping('heroes',9991,'后来改动')
        self.assertEqual(self.store.undo(),(1,1))
        self.assertEqual(self.archive.mappings(load_mappings())['matrices']['4'],'疾驰')
        self.assertEqual(self.archive.custom_mappings('heroes')['9991'],'后来改动')
    def test_invalid_file_has_no_partial_writes(self):
        b=self.bundle({'heroes':{'9991':'合法','-2':'非法'}})
        with self.assertRaises(ValueError):self.store.apply(b)
        self.assertEqual(self.archive.custom_mappings('heroes'),{})
        b=self.bundle({'battle_modes':{'1':'排位'}})
        with self.assertRaises(ValueError):validate_bundle(b)
    def test_empty_apply_preserves_last_undo_and_modes_are_not_exported(self):
        self.store.apply(self.bundle({'heroes':{'9991':'新增'}}));self.store.apply(self.bundle({}))
        self.assertEqual(self.store.undo(),(1,0))
        with self.archive.connect() as db:db.execute('INSERT INTO mappings VALUES(?,?,?)',('battle_modes','private','"test"'))
        self.assertEqual(self.store.snapshot('空')['mappings'],{})


class ScoringQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from qt_app import MainWindow
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name);self.window=MainWindow(self.archive)
    def tearDown(self):self.window.close();self.app.processEvents();close_archive(self.archive);self.tmp.cleanup()
    def test_inventory_role_filter_score_order_details_cache_and_dedup_summary(self):
        self.window.bag_snapshot={'gear':[item(1800,uid=1),item(1900,matrix=1,uid=2)],'capture_time':100}
        original=copy.deepcopy(self.window.bag_snapshot);self.window.render_inventory()
        self.window.gear_score_role.setCurrentIndex(self.window.gear_score_role.findData('speed'))
        self.window.gear_score_sort.setChecked(True)
        self.assertEqual([g['uid'] for g in self.window.gear_display],[1,2])
        self.window.gear_table.selectRow(0);self.assertIn('一速：',self.window.gear_details.toPlainText())
        self.assertIn('不使用强化次数',self.window.gear_details.toPlainText())
        with patch('qt_app.score_gear',side_effect=AssertionError('unchanged inventory was rescored')):self.window.render_inventory()
        self.assertEqual(original,self.window.bag_snapshot)
        self.window.bag_snapshot['gear'].append(copy.deepcopy(self.window.bag_snapshot['gear'][0]));self.window.render_inventory()
        self.assertIn('UID去重 2 件',self.window.gear_score_summary.text())
    def test_scoring_preset_apply_persists_and_refreshes_without_touching_inventory(self):
        from qt_app import MainWindow
        self.window.bag_snapshot={'gear':[item()],'capture_time':100};self.window.render_inventory()
        rules=default_rules();rules['name']='自定义';rules['speed']['top_factor']=2
        before=self.window.gear_scores[1]['score'];self.window.use_scoring_rules(rules)
        self.assertGreater(self.window.gear_scores[1]['score'],before)
        fresh=MainWindow(self.archive)
        try:self.assertEqual(fresh.scoring_rules,rules)
        finally:fresh.close()
    def test_native_preset_dialog_save_import_export_and_mapping_refresh(self):
        from preset_widgets import MappingPresetDialog,ScoringPresetDialog
        self.archive.set_mapping('heroes',9991,'自定义测试');self.window.mapping_changed()
        d=MappingPresetDialog(self.archive,self.window.mapping_changed,self.window)
        try:
            d.name.setText('分享包');d.save_current()
            path=Path(self.tmp.name)/'shared.json'
            with patch('preset_widgets.QFileDialog.getSaveFileName',return_value=(str(path),'')):d.export_file()
            self.assertEqual(read_bundle(path)['mappings']['heroes']['9991'],'自定义测试')
            self.assertNotIn('own_nickname',path.read_text(encoding='utf-8'))
            self.archive.remove_mapping('heroes',9991);self.window.mapping_changed()
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication
            QTimer.singleShot(0,lambda:QApplication.activeModalWidget().accept())
            with patch('preset_widgets.QMessageBox.information'):d.apply_selected()
            self.assertEqual(self.window.mappings['heroes']['9991'],'自定义测试')
            with patch('preset_widgets.QMessageBox.information'):d.undo()
            self.assertNotIn('9991',self.window.mappings['heroes'])
        finally:d.close()
        selected=[];d=ScoringPresetDialog(self.archive,default_rules(),selected.append,self.window)
        try:
            rules=default_rules();rules['name']='测试评分';rules['attribute_scale']=30
            path=Path(self.tmp.name)/'score.json';path.write_text(json.dumps(rules),encoding='utf-8')
            with patch('preset_widgets.QFileDialog.getOpenFileName',return_value=(str(path),'')):d.import_file()
            d.use_selected();self.assertEqual(selected,[rules])
        finally:d.close()
