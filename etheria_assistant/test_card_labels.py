from pathlib import Path
import unittest

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QPushButton, QWidget, QGridLayout

from battle_widgets import UnitCard
from theme import STYLE


class CardLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for name in ('msyh.ttc', 'msyhbd.ttc'):
            font = Path('C:/Windows/Fonts') / name
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        cls.app.setFont(QFont('Microsoft YaHei UI', 10))
        cls.app.setStyleSheet(STYLE)

    def make_card(self):
        unit = {
            'hero_id': 1, 'hero_name': '合成角色',
            'shells': [], 'unknown_shell_effects': [], 'matrix_effects_candidates': [], 'imprints': [],
            'stats': {'hp': 45734, 'attack': 2582, 'defense': 2360, 'speed': 350},
            'percent_attributes_tentative': {'crit': 106, 'crit_damage': 153.2,
                                           'effect_hit': 29.4, 'effect_resist': 43.4},
            'attributes_raw': [((v*10)<<8)|tag for tag,v in
                               ((171,12),(174,18),(80,0),(83,8),(58,0),(41,0))],
        }
        def action(name, callback):
            button = QPushButton(name)
            button.clicked.connect(callback)
            return button
        return UnitCard(unit, 'A', action, lambda _: None, lambda _: None, lambda _: None)

    def test_labels_and_values_survive_compact_and_wide_round_trip(self):
        card = self.make_card()
        try:
            card.show()
            for spacing in (0, 12):
                card.setStyleSheet(f'QLabel#attributeTitle {{letter-spacing:{spacing}px;}}')
                for width in (1000, 593, 510, 900, 593):
                    card.fit_width(width)
                    card.resize(width, card.minimumHeight())
                    for _ in range(10):
                        self.app.processEvents()
                    for cell in card.cells:
                        title = cell.layout().itemAt(0).widget()
                        value = cell.layout().itemAt(1).widget()
                        required_width = title.minimumSizeHint().width()
                        required_height = title.heightForWidth(title.width())
                        self.assertGreaterEqual(title.width(), required_width, (spacing, width, title.text(), title.geometry()))
                        self.assertGreaterEqual(title.height(), required_height, title.text())
                        self.assertGreaterEqual(value.width(), value.sizeHint().width(), value.text())
                        self.assertFalse(title.geometry().intersects(value.geometry()), title.text())
                        self.assertTrue(cell.rect().contains(title.geometry()), title.text())
                        self.assertTrue(cell.rect().contains(value.geometry()), value.text())
        finally:
            card.close()

    def test_eight_cards_remain_separate_with_visible_titles(self):
        host = QWidget()
        layout = QGridLayout(host)
        cards = [self.make_card() for _ in range(8)]
        for i, card in enumerate(cards):
            layout.addWidget(card, i % 4, i // 4)
        try:
            host.resize(1280, 800)
            host.show()
            for _ in range(10):
                self.app.processEvents()
            for card in cards:
                card.fit_width(card.width())
            for _ in range(10):
                self.app.processEvents()
            for i, card in enumerate(cards):
                for other in cards[i+1:]:
                    self.assertFalse(card.geometry().intersects(other.geometry()))
                for cell in card.cells[:4]:
                    title = cell.layout().itemAt(0).widget()
                    self.assertGreaterEqual(title.width(), title.minimumSizeHint().width())
                    self.assertGreaterEqual(title.height(), title.heightForWidth(title.width()))
        finally:
            host.close()

if __name__ == '__main__':
    unittest.main()
