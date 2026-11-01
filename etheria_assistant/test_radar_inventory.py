import unittest

from PySide6.QtWidgets import QApplication

from gear_scoring import default_rules
from overview_widgets import GearOverview


class InventoryRadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_depth_and_quality_use_different_denominators(self):
        scores = {uid: {'score': 50, 'complete': True, 'roles': [
            {'key': 'attack', 'score': 50, 'eligible': True},
            {'key': 'accuracy', 'score': 40, 'eligible': True},
            {'key': 'resistance', 'score': 60, 'eligible': True},
            {'key': 'defense', 'score': 99, 'eligible': False},
        ]} for uid in range(12)}
        panel = GearOverview(n=5)
        try:
            panel.set_scores(scores, default_rules())
            axes = {a['key']: a for a in panel.radar.axes}
            self.assertTrue(panel.radar.count_mode)
            self.assertEqual(axes['attack']['eligible_count'], 12)
            self.assertEqual(axes['support']['eligible_count'], 12)
            self.assertEqual(axes['defense']['eligible_count'], 0)
            self.assertEqual(panel.radar.scale, 15)
            self.assertEqual(axes['attack']['count'], 5)
            self.assertEqual(axes['attack']['percent'], 50)
            panel.mode.setCurrentIndex(1)
            self.assertFalse(panel.radar.count_mode)
            self.assertEqual(panel.radar.scale, 100)
            panel.n.setValue(2)
            self.assertEqual(panel.metrics['axes'][1]['count'], 2)
            panel.mode.setCurrentIndex(0)
            self.assertEqual(panel.metrics['axes'][1]['eligible_count'], 12)
            self.assertTrue(panel.n.isHidden())
        finally:
            panel.close()

    def test_empty_fold_and_small_width(self):
        panel = GearOverview()
        try:
            panel.set_scores({}, default_rules())
            panel.resize(780, 240)
            panel.show()
            self.app.processEvents()
            self.assertTrue(panel.radar.isVisible())
            self.assertEqual(len(panel.radar.targets), 6)
            self.assertGreater(panel.radar.scale, 0)
            panel.toggle.setChecked(False)
            self.assertTrue(panel.radar.isHidden() or not panel.radar.isVisible())
            panel.toggle.setChecked(True)
            self.assertTrue(panel.radar.isVisible())
            self.assertTrue(panel.n.isHidden())
        finally:
            panel.close()
