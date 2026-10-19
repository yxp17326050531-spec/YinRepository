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
QPushButton#nav {background:transparent; border:0; padding:9px 0; color:#a79eb8; font-size:13px;}
QPushButton#nav:checked {background:#252036; color:#81dcfa; border-left:3px solid #59ccef; border-radius:5px;}
QPushButton#link {border:0; padding:2px; text-align:left; background:transparent; font-weight:700; font-size:16px;}
QPushButton#link:hover {color:#70deca;}
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
QPushButton#heroMore {padding:0 5px; font-size:17px; border:0; background:transparent;}
QMenu {background:#211c2b; border:1px solid #4a3d59; padding:4px;}
QMenu::item {padding:8px 20px;}
QMenu::item:selected {background:#3b3152;}
QDialog {background:#1c1925;}
QCheckBox {spacing:8px;}
QFrame#heroRow QFrame#extraAttributes {background:#17141f; border:0; border-radius:5px;}
QLabel#teamOutcome {font-size:13px; font-weight:700; padding:4px 8px; border-radius:5px; background:#282332; color:#aaa1b8;}
QLabel#teamOutcome[result=win] {background:#183b31; color:#61d7a0;}
QLabel#teamOutcome[result=loss] {background:#42242f; color:#f18798;}
'''
