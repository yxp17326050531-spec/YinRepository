"""Dark competitive theme with small local reference artwork."""
STYLE = '''
QWidget { background:#09141e; color:#dce5f0; font-family:"Microsoft YaHei UI","Noto Sans CJK SC","Noto Sans SC","sans-serif"; font-size:14px; }
QMainWindow, QScrollArea, QStackedWidget {background:#09141e;}
QFrame#sidebar {background:#0c1925; border-right:1px solid #253044;}
QLabel#brand {font-size:20px; font-weight:700; color:#f0f5fc;}
QLabel#title {font-size:22px; font-weight:700;}
QLabel#hint {color:#8393aa; background:transparent;}
QLabel#eyebrow {color:#56d8bf; font-size:11px; font-weight:700; letter-spacing:2px;}
QLabel#metric {font-size:24px; font-weight:700; color:#eaf2ff; background:transparent;}
QLabel#speed {color:#ffcc42; font-size:20px; font-weight:700; background:transparent;}
QLabel#hero {font-size:16px; font-weight:700; background:transparent;}
QLabel#avatar {background:#26394a; color:#70deca; border:1px solid #385468; border-radius:10px; font-size:20px; font-weight:700;}
QFrame#card {background:#0d1c28; border:1px solid #1d3546; border-radius:6px;}
QFrame#card QLabel, QFrame#card QWidget#transparent {background:transparent;}
QFrame#heroCard {background:#10212e; border:1px solid #1d3546; border-radius:9px;}
QFrame#heroCard QLabel {background:transparent;}
QPushButton {background:#243246; border:1px solid #35455d; border-radius:7px; padding:8px 13px; color:#dce6f2;}
QPushButton:hover {background:#30435b; border-color:#53a79d;}
QPushButton#filterChip {text-align:left; background:#152635; border:1px solid #31495a; padding:10px 14px;}
QPushButton#filterChip:checked {background:#17473f; border:2px solid #36d2b7; color:#adffe8;}
QPushButton:pressed {background:#162f35;}
QPushButton:disabled {color:#58677b; background:#1b2431; border-color:#263246;}
QPushButton#primary {background:#16d6bd; color:#102920; border:0; font-weight:700;}
QPushButton#primary:hover {background:#73e2ca;}
QPushButton#nav {background:transparent; border:0; padding:11px 0; color:#9babc1; font-size:21px;}
QPushButton#nav:checked {background:#122e3c; color:#76e4cf; border-left:3px solid #16d6bd; border-radius:5px;}
QPushButton#link {border:0; padding:2px; text-align:left; background:transparent; font-weight:700; font-size:16px;}
QPushButton#link:hover {color:#70deca;}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {background:#111b29; border:1px solid #34445b; border-radius:6px; padding:7px; selection-background-color:#30685f;}
QComboBox QAbstractItemView {background:#1c293b; selection-background-color:#275950;}
QTableWidget {background:#0d1c28; alternate-background-color:#102330; border:1px solid #1d3546; border-radius:8px; gridline-color:#263347; selection-background-color:#2b5655; selection-color:#edfffa;}
QHeaderView::section {background:#102330; color:#94a8c2; border:0; border-bottom:1px solid #35455c; padding:10px; font-weight:600;}
QTableWidget::item {padding:6px; border-bottom:1px solid #263246;}
QTabWidget::pane {border:0;}
QTabBar::tab {padding:10px 17px; background:#182233; color:#93a8c3; border-bottom:2px solid transparent;}
QTabBar::tab:selected {color:#77e2cb; border-bottom:2px solid #51cbb2;}
QScrollBar:vertical {background:#131c29; width:9px; margin:0;}
QScrollBar::handle:vertical {background:#344861; border-radius:4px; min-height:30px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QScrollBar:horizontal {background:#131c29; height:9px;}
QScrollBar::handle:horizontal {background:#344861; border-radius:4px; min-width:30px;}
QStatusBar {background:#141d2b; color:#8fa4bc;}
QToolTip {background:#26374b; color:#e8f3ff; border:1px solid #53aa9d; padding:5px;}
QFrame#heroRow {background:transparent; border:0; border-top:1px solid #1d3546;}
QFrame#heroRow QWidget, QFrame#heroRow QLabel {background:transparent;}
QLabel#ownTeam {color:#49d0fc; font-size:19px; font-weight:700; border-left:4px solid #24b6fa; padding-left:10px;}
QLabel#enemyTeam {color:#ff596b; font-size:19px; font-weight:700; border-left:4px solid #ff425c; padding-left:10px;}
QLabel#statValue {color:#e2ebf5; font-size:18px; font-weight:600;}
QLabel#attributeTitle {color:#a1b1c5; font-size:12px;}
QPushButton#smallAction {padding:4px 7px; font-size:12px; background:#152c3b; border-color:#254255;}
QPushButton#link {font-size:17px;}
QLabel#shell {font-size:15px; font-weight:600;}
QLabel#matrixName {font-size:15px;}
QLabel#artIcon {background:#192e3b; border-radius:5px; color:#9de5d6; font-size:18px;}
QFrame#teamCard {background:#0d1c28; border:1px solid #1d3546; border-radius:6px;}
QFrame#teamCard QLabel {background:transparent;}
QLabel#teamBadge {font-size:12px; color:#8ba3b8; padding-right:4px;}
QLabel#teamNeutral {font-size:18px; font-weight:700; color:#b9d4e5;}
QLabel#battleStatus {color:#b4d7cf; font-size:14px;}
QPushButton#heroMore {padding:0 5px; font-size:17px; border:0; background:transparent;}
QMenu {background:#142431; border:1px solid #30495c; padding:4px;}
QMenu::item {padding:8px 20px;}
QMenu::item:selected {background:#24564f;}
QDialog {background:#0d1c28;}
QCheckBox {spacing:8px;}
'''
