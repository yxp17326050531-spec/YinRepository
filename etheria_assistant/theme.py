"""Dark competitive theme with small local reference artwork."""
STYLE = '''
QWidget { background:#121018; color:#dce5f0; font-family:"Microsoft YaHei UI","Noto Sans CJK SC","Noto Sans SC","sans-serif"; font-size:14px; }
QMainWindow, QScrollArea, QStackedWidget {background:#121018;}
QFrame#sidebar {background:#100e16; border-right:1px solid #302a3c;}
QLabel#brand {font-size:20px; font-weight:700; color:#f0f5fc;}
QLabel#title {font-size:22px; font-weight:700;}
QLabel#hint {color:#a29aaf; background:transparent;}
QLabel#eyebrow {color:#56d8bf; font-size:11px; font-weight:700; letter-spacing:2px;}
QLabel#metric {font-size:24px; font-weight:700; color:#eaf2ff; background:transparent;}
QLabel#speed {color:#ffcc42; font-size:20px; font-weight:700; background:transparent;}
QLabel#hero {font-size:16px; font-weight:700; background:transparent;}
QLabel#avatar {background:#26394a; color:#70deca; border:1px solid #385468; border-radius:10px; font-size:20px; font-weight:700;}
QFrame#card {background:#1c1925; border:1px solid #302a3c; border-radius:6px;}
QFrame#card QLabel, QFrame#card QWidget#transparent {background:transparent;}
QFrame#heroCard {background:#201c2b; border:1px solid #302a3c; border-radius:9px;}
QFrame#heroCard QLabel {background:transparent;}
QPushButton {background:#292332; border:1px solid #40364d; border-radius:7px; padding:8px 13px; color:#dce6f2;}
QPushButton:hover {background:#362f42; border-color:#53a79d;}
QPushButton#filterChip {text-align:left; background:#152635; border:1px solid #31495a; padding:10px 14px;}
QPushButton#filterChip:checked {background:#17473f; border:2px solid #36d2b7; color:#adffe8;}
QPushButton:pressed {background:#162f35;}
QPushButton:disabled {color:#58677b; background:#1b2431; border-color:#263246;}
QPushButton#primary {background:#59ccef; color:#0c2631; border:0; font-weight:700;}
QPushButton#primary:hover {background:#73e2ca;}
QToolButton#nav {background:transparent; border:0; padding:7px 0; color:#a79eb8; font-size:13px;}
QToolButton#nav:checked {background:#252036; color:#81dcfa; border-left:3px solid #59ccef; border-radius:5px;}
QFrame#overviewHeader {background:transparent; border:0;}
QFrame#overviewHeader QLabel {background:transparent;}
QFrame#gearOverview {background:#1c1925; border:1px solid #3c334b; border-radius:10px;}
QPushButton#gearOverviewToggle {text-align:left; border:0; background:transparent; color:#ded5ed; padding:3px; font-size:14px; font-weight:600;}
QLabel#gearOverviewBadge {color:#70dcce;}
QLabel#gearOverviewCaption {color:#c6bcd2;}
QLabel#gearOverviewScoreLabel {color:#b6a4ca;}
QLabel#gearOverviewCounts {color:#d0c7dd;}
QLabel#gearOverviewNote {color:#9d92ac;}
QLabel#gearOverviewSpeed {color:#d4c6e4;}
QLabel#gearOverviewSpeedCount {color:#e1d8eb;}
QLabel#gearOverviewHighlight {color:#ffd170;}
QLabel#gearOverviewFooter {color:#bdb3cb;}
QPushButton#link {border:0; padding:2px; text-align:left; background:transparent; font-weight:700; font-size:16px;}
QPushButton#link:hover {color:#70deca;}
QPushButton#link[fullPotential="true"], QPushButton#link[fullPotential="true"]:hover {color:#ffd477;}
QLabel#componentHint {color:#a9b8cc; font-size:12px;}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {background:#1c1926; border:1px solid #40364d; border-radius:6px; padding:7px; selection-background-color:#30685f;}
QComboBox QAbstractItemView {background:#272132; selection-background-color:#3b3152;}
QTableWidget {background:#1c1925; alternate-background-color:#211d2b; border:1px solid #302a3c; border-radius:8px; gridline-color:#263347; selection-background-color:#2b5655; selection-color:#edfffa;}
QHeaderView::section {background:#211d2b; color:#b1a5c2; border:0; border-bottom:1px solid #35455c; padding:10px; font-weight:600;}
QTableWidget::item {padding:6px; border-bottom:1px solid #263246;}
QTabWidget::pane {border:0;}
QTabBar::tab {padding:10px 17px; background:#182233; color:#93a8c3; border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#77e2cb; border-bottom:2px solid #51cbb2;}
QScrollBar:vertical {background:#17141f; width:9px; margin:0;}
QScrollBar::handle:vertical {background:#453b52; border-radius:4px; min-height:30px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QScrollBar:horizontal {background:#17141f; height:9px;}
QScrollBar::handle:horizontal {background:#453b52; border-radius:4px; min-width:30px;}
QStatusBar {background:#191520; color:#aca0bb;}
QToolTip {background:#30273d; color:#e8f3ff; border:1px solid #53aa9d; padding:5px;}
QFrame#heroRow {background:#1c1925; border:1px solid #302a3c; border-radius:8px;}
QFrame#heroRow QWidget, QFrame#heroRow QLabel {background:transparent;}
QLabel#ownTeam {color:#49d0fc; font-size:19px; font-weight:700; border-left:4px solid #24b6fa; padding-left:10px;}
QLabel#enemyTeam {color:#ba9cf7; font-size:19px; font-weight:700; border-left:4px solid #a48be8; padding-left:10px;}
QLabel#statValue {color:#e2ebf5; font-size:18px; font-weight:600;}
QLabel#attributeTitle {color:#aca3b8; font-size:12px;}
QPushButton#heroMore::menu-indicator {image:none; width:0;}
QPushButton#smallAction {padding:4px 7px; font-size:12px; background:#24202f; border-color:#40364d;}
QPushButton#link {font-size:17px;}
QLabel#shell {font-size:15px; font-weight:600;}
QLabel#matrixName {font-size:13px;}
QLabel#artIcon {background:#2a2535; border-radius:5px; color:#9de5d6; font-size:18px;}
QFrame#teamCard {background:transparent; border:0;}
QFrame#teamCard QLabel {background:transparent;}
QLabel#teamBadge {font-size:12px; color:#8ba3b8; padding-right:4px;}
QLabel#teamNeutral {font-size:18px; font-weight:700; color:#d1c6e2;}
QLabel#battleStatus {color:#b4d7cf; font-size:14px;}
QFrame#openingTurnStrip {background:#1b1724; border:1px solid #382e44; border-radius:7px;}
QWidget#openingTurnTrack, QWidget#openingMarker, QLabel#openingMetric,
QLabel#openingTurnTitle, QFrame#openingPortraitRing QLabel#artIcon {background:transparent;}
QLabel#openingTurnTitle {color:#ded3ea; font-size:13px; font-weight:700;}
QLabel#openingMetric {color:#ece5f5; font-size:16px; font-weight:700;}
QPushButton#openingMode {padding:3px 6px; font-size:12px; background:#24202f; border-color:#40364d;}
QPushButton#openingMode:checked {color:#77e2cb; border-color:#51cbb2;}
QFrame#openingPortraitRing {border-radius:15px; background:#241d30;}
QFrame#openingPortraitRing[side=own] {border:2px solid #49d0fc;}
QFrame#openingPortraitRing[side=enemy] {border:2px solid #ba9cf7;}
QPushButton#heroMore {padding:0 5px; font-size:17px; border:0; background:transparent;}
QMenu {background:#211c2b; border:1px solid #4a3d59; padding:4px;}
QMenu::item {padding:8px 20px;}
QMenu::item:selected {background:#3b3152;}
QDialog {background:#1c1925;}
QCheckBox {spacing:8px;}
QDialog#battleAttributeSettings QCheckBox::indicator:unchecked {border:1px solid #746786; border-radius:3px;}
QFrame#heroRow QFrame#extraAttributes {background:#17141f; border:0; border-radius:5px;}
QLabel#teamOutcome {font-size:13px; font-weight:700; padding:4px 8px; border-radius:5px; background:#282332; color:#aaa1b8;}
QLabel#teamOutcome[result=win] {background:#183b31; color:#61d7a0;}
QLabel#teamOutcome[result=loss] {background:#42242f; color:#f18798;}
'''

THEMES = {'gold': '暖黑古金', 'classic': '经典紫黑'}
DEFAULT_THEME = 'gold'

GOLD_STYLE = '''
QWidget {background:#12110f; color:#efe7d8;}
QMainWindow, QScrollArea, QStackedWidget {background:#12110f;}
QFrame#sidebar {background:#161410; border-right:1px solid #494032;}
QLabel#brand {color:#d4b477;}
QLabel#hint, QLabel#componentHint {color:#b8ac99;}
QLabel#title {color:#efe7d8; font-size:25px;}
QLabel#speed {color:#eac584;}
QFrame#card, QFrame#heroCard, QFrame#heroRow {background:#1d1b18; border:1px solid #494032;}
QFrame#heroRow QFrame#extraAttributes {background:#171511;}
QLabel#statValue {color:#efe7d8;}
QLabel#attributeTitle, QLabel#battleStatus, QLabel#teamBadge {color:#b8ac99;}
QLabel#teamNeutral {color:#e1d4bc;}
QLabel#artIcon {background:#302b24; color:#d4b477;}
QFrame#overviewHeader[decorated=true] {background:#1b1814; border:1px solid #5f503a; border-radius:7px;}
QFrame#gearOverview {background:#1d1b18; border-color:#5f503a;}
QPushButton#gearOverviewToggle, QLabel#gearOverviewCounts, QLabel#gearOverviewSpeed,
QLabel#gearOverviewSpeedCount {color:#efe7d8;}
QLabel#gearOverviewBadge, QLabel#gearOverviewHighlight {color:#eac584;}
QLabel#gearOverviewCaption, QLabel#gearOverviewScoreLabel,
QLabel#gearOverviewNote, QLabel#gearOverviewFooter {color:#b8ac99;}
QToolButton#nav {color:#b8ac99;}
QToolButton#nav:checked {background:#242019; color:#d7b77b; border-left:3px solid #d7b77b;}
QPushButton {background:#24201b; border-color:#5c4e3b; color:#efe7d8;}
QPushButton:hover {background:#332c22; border-color:#b2996d;}
QPushButton:pressed {background:#3a3024;}
QPushButton:disabled {color:#8d806b; background:#201c16; border-color:#3a3227;}
QPushButton#primary {background:#d7b77b; color:#22190f;}
QPushButton#primary:hover {background:#e7cc96;}
QPushButton#link:hover {color:#d4b477;}
QPushButton#smallAction, QPushButton#openingMode {background:#24201b; border-color:#5c4e3b;}
QPushButton#openingMode:checked {color:#eac584; border-color:#b2996d;}
QFrame#openingTurnStrip {background:#1b1814; border-color:#5f503a;}
QFrame#openingPortraitRing {background:#252018;}
QLabel#openingTurnTitle, QLabel#openingMetric {color:#efe7d8;}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {background:#1b1814; border-color:#5c4e3b; selection-background-color:#57452b;}
QComboBox QAbstractItemView, QMenu {background:#242019; border-color:#5c4e3b; selection-background-color:#483a27;}
QMenu::item:selected {background:#483a27;}
QTableWidget {background:#1d1b18; alternate-background-color:#24211b; border-color:#494032;
    gridline-color:#3a3125; selection-background-color:#57452b; selection-color:#fff4dd;}
QHeaderView::section {background:#252019; color:#d0bea0; border-bottom-color:#5c4e3b;}
QTableWidget::item {border-bottom-color:#3a3125;}
QTabBar::tab {background:#221e18; color:#b8ac99;}
QTabBar::tab:selected {color:#eac584; border-bottom-color:#d4b477;}
QScrollBar:vertical, QScrollBar:horizontal {background:#171511;}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {background:#574932;}
QDialog, QStatusBar {background:#1b1814; color:#b8ac99;}
QToolTip {background:#30271d; color:#efe7d8; border-color:#89734f;}
QLabel#teamOutcome[result=unknown] {background:#2c261e; color:#b8ac99;}
'''


def interface_style(theme):
    return STYLE + GOLD_STYLE if theme == 'gold' else STYLE
