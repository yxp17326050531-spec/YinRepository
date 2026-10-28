"""Read-only total, fixed-reference radar and compact native layout behavior."""
import copy
import tempfile
import unittest
from gear_scoring import default_rules,score_gear
from gear_overview import overview_metrics
from core import load_mappings
from test_inventory_scoring import item,close_archive


class OverviewTests(unittest.TestCase):
    def test_total_matches_highest_use_not_axis_sum_and_support_does_not_double_count(self):
        scores={1:{'score':60,'complete':True,'roles':[
            {'key':'accuracy','score':40,'eligible':True},
            {'key':'resistance','score':60,'eligible':True},
            {'key':'speed','score':None,'eligible':False,'speed':18.5}]}}
        result=overview_metrics(scores,default_rules())
        self.assertEqual(result['total'],60)
        support=next(a for a in result['axes'] if a['key']=='support')
        self.assertEqual(support['raw'],60);self.assertEqual(support['count'],1)
        self.assertEqual(result['speed_bins']['19'],1)
    def test_reference_is_fixed_not_normalized_to_own_strongest_axis(self):
        scores={1:{'score':50,'complete':True,'roles':[{'key':'attack','score':50,'eligible':True}]}}
        a=overview_metrics(scores,default_rules(),5)['axes'][1]
        b=overview_metrics(scores,default_rules(),10)['axes'][1]
        self.assertEqual(a['raw'],50);self.assertEqual(a['percent'],10)
        self.assertEqual(b['percent'],5)
        scores[2]=copy.deepcopy(scores[1]);c=overview_metrics(scores,default_rules(),5)['axes'][1]
        self.assertEqual(c['percent'],20)
    def test_empty_and_zero_reference_are_explicit_and_overflow_is_only_visually_clipped(self):
        empty=overview_metrics({},default_rules());self.assertEqual(empty['count'],0);self.assertEqual(empty['total'],0)
        rules=default_rules();rules['roles']['attack']['weights']={k:0 for k in rules['roles']['attack']['weights']}
        self.assertIsNone(overview_metrics({},rules)['axes'][1]['percent'])
        scores={1:{'score':600,'complete':True,'roles':[{'key':'attack','score':600,'eligible':True}]}}
        a=overview_metrics(scores,default_rules(),1)['axes'][1]
        self.assertEqual(a['raw'],600);self.assertEqual(a['percent'],600);self.assertEqual(a['draw_percent'],100)
    def test_raw_data_and_scores_are_not_mutated_and_only_top_n_contribute(self):
        rules=default_rules();raw=[item(1800,uid=1),item(1950,uid=2)];before=copy.deepcopy(raw)
        scores={g['uid']:score_gear(g,load_mappings(),rules) for g in raw};original=copy.deepcopy(scores)
        result=overview_metrics(scores,rules,1)
        self.assertEqual(result['axes'][0]['count'],1)
        self.assertEqual(result['speed_bins']['20+'],1)
        self.assertEqual(raw,before);self.assertEqual(scores,original)


class OverviewQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from storage import Archive
        from qt_app import MainWindow
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name);self.window=MainWindow(self.archive)
    def tearDown(self):
        self.window.close();self.app.processEvents();close_archive(self.archive);self.tmp.cleanup()
    def test_filter_does_not_change_total_and_fold_preferences_survive_restart(self):
        from qt_app import MainWindow
        self.window.bag_snapshot={'gear':[item(uid=1),item(1950,uid=2)],'capture_time':100};self.window.render_inventory();self.window.navigate(2)
        overview=self.window.gear_overview;total=overview.metrics['total']
        self.window.gear_query.setText('no match');self.assertEqual(self.window.gear_table.rowCount(),0)
        self.assertEqual(overview.metrics['total'],total)
        overview.toggle.setChecked(False);overview.n.setValue(3)
        self.assertTrue(overview.body.isHidden());self.assertIn('总分',overview.toggle.text())
        fresh=MainWindow(self.archive)
        try:
            self.assertFalse(fresh.gear_overview.toggle.isChecked());self.assertEqual(fresh.gear_overview.n.value(),3)
        finally:fresh.close()
    def test_normal_window_keeps_chart_and_list_visible_and_collapse_returns_space(self):
        self.window.bag_snapshot={'gear':[item(uid=1)],'capture_time':100};self.window.render_inventory();self.window.navigate(2);self.window.show()
        self.window.resize(1280,800)
        for _ in range(5):self.app.processEvents()
        overview=self.window.gear_overview;table=self.window.gear_table
        self.assertTrue(overview.radar.isVisible());self.assertGreater(table.viewport().height(),35)
        self.assertEqual(len(overview.radar.axes),6)
        self.assertTrue(overview.radar.accessibleDescription())
        before=table.height();overview.toggle.setChecked(False)
        for _ in range(5):self.app.processEvents()
        self.assertGreater(table.height(),before)
