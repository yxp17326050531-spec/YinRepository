"""PySide6 desktop UI. Local archive and capture protocol remain framework independent."""
from __future__ import annotations
import copy
import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl, QEvent
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QLineEdit, QSpinBox, QCheckBox, QPlainTextEdit, QTabWidget, QDialog,
    QDialogButtonBox, QFormLayout, QFileDialog, QMessageBox, QButtonGroup, QSplitter, QBoxLayout, QMenu, QSizePolicy)
from capture_events import CaptureEvents
from capture import CaptureJob, find_dumpcap, shell_text, matrix_text, imprint_text, HIDE_CONSOLE
from core import load_mappings, shell_config_name, matrix_name
from storage import Archive, project_unit, unit_key, shell_candidates
from analytics import analyse, rank_statistics
from theme import STYLE
from battle_widgets import unit_card
from equipment import (project_gear, attribute_text, matches_gear, normalize_filters,
                       filter_options, filter_summary, RARITIES, UNKNOWN, ATTRIBUTES,
                       normalize_sort, sort_gear, gear_sort_value)
from inventory_widgets import GearFilterDialog
from components import project_component, attribute_text as component_attribute_text, component_detail as component_detail_text
from battle_attributes import decode_extra_attributes, pending_attributes, pending_text, extra_text

VERSION='2.11.3-calc-test'
CATEGORIES={'角色编号':'heroes','智壳配置编号':'shell_configs','智壳战斗效果编号':'shell_effects',
            '矩阵库存编号':'matrices','矩阵战斗效果编号':'matrix_effects'}
from battle_metadata import KINDS, result_text

def label(text, name=None):
    w=QLabel(str(text)); w.setWordWrap(True);w.setTextFormat(Qt.TextFormat.PlainText)
    if name:w.setObjectName(name)
    return w

def button(text, action, primary=False):
    w=QPushButton(text); w.clicked.connect(lambda checked=False: action())
    if primary:w.setObjectName('primary')
    return w

def combo(items, current=None):
    w=QComboBox(); w.addItems(items)
    if current is not None:w.setCurrentText(str(current))
    return w

def table(headers):
    w=QTableWidget(0,len(headers)); w.setHorizontalHeaderLabels(headers)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setAlternatingRowColors(True); w.verticalHeader().hide()
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    w.horizontalHeader().setResizeContentsPrecision(100)
    w.horizontalHeader().setStretchLastSection(True); w.setWordWrap(False)
    w.verticalHeader().setDefaultSectionSize(42)
    return w

def fill(w, rows):
    w.setUpdatesEnabled(False);blocked=w.blockSignals(True)
    try:
        w.setRowCount(len(rows))
        for r,values in enumerate(rows):
            for c,value in enumerate(values):
                item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); w.setItem(r,c,item)
        # Resize once after the batch. ResizeToContents on each change causes
        # repeated size-hint work while large hidden tables are populated.
        w.resizeColumnsToContents()
        for column in range(w.columnCount()):w.setColumnWidth(column,min(w.columnWidth(column),400))
    finally:w.blockSignals(blocked);w.setUpdatesEnabled(True)


def delete_shortcut(widget,action):
    shortcut=QShortcut(QKeySequence('Delete'),widget,activated=action)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    return shortcut

def stamp(value):
    return datetime.fromtimestamp(value).strftime('%m-%d %H:%M:%S') if value else '未知时间'

def percent(value):return '—' if value is None else f'{value*100:.1f}%'

def parse_matrices(text):
    out=[]
    for line in text.splitlines():
        if not line.strip():continue
        parts=line.replace('，',',').rsplit(',',1)
        if len(parts)!=2:raise ValueError('每行填写“名称,点数”，例如 狂怒,9')
        out.append({'name':parts[0].strip(),'points':int(parts[1])})
    return out

class Editor(QDialog):
    """Scrollable body with always-visible Save / Cancel actions."""
    def __init__(self,parent,title):
        super().__init__(parent); self.setWindowTitle(title); self.resize(610,570)
        root=QVBoxLayout(self); root.addWidget(label(title,'hero'))
        scroll=QScrollArea(); scroll.setWidgetResizable(True); root.addWidget(scroll,1)
        body=QWidget(); self.form=QFormLayout(body); self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); scroll.setWidget(body)
        self.actions=QHBoxLayout(); root.addLayout(self.actions)
        self.save=button('保存修改',self.commit,True); self.actions.addWidget(self.save)
        self.actions.addStretch(); self.actions.addWidget(button('取消',self.reject))
        QShortcut(QKeySequence('Ctrl+Return'),self,activated=self.commit)
        self.on_save=lambda:None
    def commit(self):
        try:self.on_save(); self.accept()
        except Exception as exc:QMessageBox.warning(self,'无法保存',str(exc))

class MainWindow(QMainWindow):
    def __init__(self,archive=None):
        super().__init__(); self.archive=archive or Archive(); self.preferences=self.archive.settings()
        self.mappings=self.archive.mappings(load_mappings()); self.events=CaptureEvents(128)
        self._mapping_undo=None
        self._stats_dirty=True;self._stats_signature=None;self._battle_dirty=True;self._inventory_dirty=True
        self.history_query='';self._history_search_dirty=True
        self.job=None; self.token=0; self.current_id=None; self.live_id=None; self.browsing=False
        self.live_time=None; self.capture_diagnostics=self.preferences.get('last_capture_diagnostics',{})
        self.latest=None; self.unsaved_battle=None; self.storage_failed=False; self.inventory_rows=[]; self.history_offset=0; self.history_ids=[]
        saved=self.archive.latest_inventory(); self.bag_snapshot=saved['data'] if saved else None
        self.gear_filters=normalize_filters(self.preferences.get('gear_filters',{}))
        self.gear_sort=normalize_sort(self.preferences.get('gear_sort',{}))
        self.gear_metadata=self.archive.gear_metadata()
        if self.bag_snapshot:self.inventory_rows=self.bag_snapshot.get('loadout_rows',[])
        self.setWindowTitle('伊瑟 · 对局助手 '+VERSION); self.resize(1280,800); self.setMinimumSize(1050,700)
        self.setStyleSheet(STYLE); self.setup(); self.refresh_all()
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(80)
        self.set_topmost(self.preferences.get('topmost',False))
        self.archive.logger.info('Qt application %s started',VERSION)
        if not self.preferences.get('interface_id'):self.navigate(5)

    def guarded(self,action):
        try:return action()
        except Exception as exc:
            self.archive.logger.exception('UI action failed'); QMessageBox.warning(self,'操作失败',str(exc))
    def action(self,text,fn,primary=False):return button(text,lambda:self.guarded(fn),primary)
    def notify(self,text):self.statusBar().showMessage(str(text))
    def setup(self):
        central=QWidget(); self.setCentralWidget(central); outer=QHBoxLayout(central); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(60); s=QVBoxLayout(side); s.setContentsMargins(4,14,4,12)
        brand=label('伊','brand');brand.setAlignment(Qt.AlignmentFlag.AlignCenter);s.addWidget(brand);s.addSpacing(16)
        self.nav=QButtonGroup(self); self.stack=QStackedWidget()
        for i,(icon,title) in enumerate(zip(['◈','▥','▦','◷','⌘','⚙'],['对局总览','战绩统计','源器与配装','历史与日志','编号映射','连接与设置'])):
            b=QPushButton(icon+'\n'+['对局','战绩','配装','日志','映射','设置'][i]);b.setToolTip(title);b.setAccessibleName(title);b.setCheckable(True);b.setObjectName('nav');self.nav.addButton(b,i);s.addWidget(b)
        self.nav.idClicked.connect(self.navigate);s.addStretch()
        self.version_label=label(VERSION,'hint');self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.version_label.setToolTip(VERSION);s.addWidget(self.version_label);outer.addWidget(side)
        main=QWidget(); m=QVBoxLayout(main); m.setContentsMargins(12,10,12,8); m.setSpacing(8)
        top=QHBoxLayout(); self.page_title=label('对局总览','title'); top.addWidget(self.page_title); top.addStretch()
        self.connection=label('●  未监听','hint'); top.addWidget(self.connection)
        self.import_btn=self.action('导入抓包',self.import_capture); top.addWidget(self.import_btn)
        self.start_btn=self.action('开始监听',self.start_live,True); top.addWidget(self.start_btn)
        self.stop_btn=self.action('停止',self.stop_capture); self.stop_btn.setEnabled(False); top.addWidget(self.stop_btn); m.addLayout(top)
        m.addWidget(self.stack,1); outer.addWidget(main,1)
        self.build_battle(); self.build_stats(); self.build_inventory(); self.build_history(); self.build_mappings(); self.build_settings()
        self.navigate(0); self.notify('就绪')
    def navigate(self,index):
        self.stack.setCurrentIndex(index); self.nav.button(index).setChecked(True)
        self.page_title.setText(['对局总览','战绩统计','源器与配装','历史与日志','编号映射','连接与设置'][index])
        if index==1 and self._stats_dirty:self.refresh_stats()
        if index==3:self.refresh_history()
        if index==0 and self._battle_dirty and hasattr(self,'history_filter'):self.render_battle()
        if index==2 and self._inventory_dirty and hasattr(self,'history_filter'):self.render_inventory()
    def page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0); layout.setSpacing(8); self.stack.addWidget(page); return layout
    def card(self):
        card=QFrame(); card.setObjectName('card'); layout=QVBoxLayout(card); layout.setContentsMargins(14,14,14,14); layout.setSpacing(12); return card,layout
    def build_battle(self):
        layout=self.page();bar=QHBoxLayout();bar.setSpacing(6)
        self.previous_battle=self.action('‹',lambda:self.step_battle(1));self.previous_battle.setToolTip('上一场 · Alt+左');bar.addWidget(self.previous_battle)
        self.next_battle=self.action('›',lambda:self.step_battle(-1));self.next_battle.setToolTip('下一场 · Alt+右');bar.addWidget(self.next_battle)
        self.battle_jump=QComboBox();self.battle_jump.setMinimumContentsLength(16);self.battle_jump.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.battle_jump.currentIndexChanged.connect(self.jump_battle);bar.addWidget(self.battle_jump,1)
        self.battle_position=label('','hint');bar.addWidget(self.battle_position)
        self.battle_info=label('等待对局','battleStatus');self.battle_info.setWordWrap(False);bar.addWidget(self.battle_info)
        bar.addWidget(self.action('最新',self.return_live));bar.addWidget(self.action('校正',self.edit_context))
        bar.addWidget(self.action('伤害试算',self.show_damage_calculator))
        more=self.action('更多',lambda:None);menu=QMenu(more)
        for title,fn in [('记录信息',self.show_record_info),('读取诊断',self.show_capture_diagnostics),('导出本场',self.export_battle),('返回历史日志',self.back_to_history),('缓存与保存',self.show_capture_storage)]:menu.addAction(title,lambda checked=False,f=fn:self.guarded(f))
        more.setMenu(menu);bar.addWidget(more);layout.addLayout(bar)
        # Detailed status stays available in the record dialog, not above rosters.
        self.record_info=label('','hint');self.record_info.setParent(self.stack.widget(0));self.record_info.hide()
        self.capture_info=label('尚未开始本次采集','hint');self.capture_info.setParent(self.stack.widget(0));self.capture_info.hide()
        QShortcut(QKeySequence('Alt+Left'),self,activated=lambda:self.step_battle(1) if self.stack.currentIndex()==0 else None)
        QShortcut(QKeySequence('Alt+Right'),self,activated=lambda:self.step_battle(-1) if self.stack.currentIndex()==0 else None)
        scroll=QScrollArea();self.battle_scroll=scroll;scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);layout.addWidget(scroll,1)
        content=QWidget();body=QVBoxLayout(content);body.setContentsMargins(0,0,0,0);body.setSpacing(0);scroll.setWidget(content)
        teams=QBoxLayout(QBoxLayout.Direction.LeftToRight);self.teams_layout=teams;teams.setSpacing(10)
        self.team_layouts={};self.team_titles={};self.nickname_buttons={};self.team_cards={};self.team_outcomes={}
        for team in ['A','B']:
            card,c=self.card();card.setObjectName('teamCard');c.setContentsMargins(0,0,0,0);c.setSpacing(8);self.team_cards[team]=card
            header=QHBoxLayout();badge=label(team,'teamBadge');header.addWidget(badge);title=label('记录 '+team+' 方','teamNeutral');title.setWordWrap(False);title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);header.addWidget(title,1)
            assign=self.action('对应昵称',self.assign_nicknames);assign.setObjectName('smallAction');header.addWidget(assign)
            self.nickname_buttons[team]=assign;self.team_titles[team]=title
            outcome=label('待确认','teamOutcome');outcome.setWordWrap(False);header.addWidget(outcome);self.team_outcomes[team]=outcome;c.addLayout(header)
            roster=QVBoxLayout();roster.setSpacing(8);c.addLayout(roster);c.addStretch();self.team_layouts[team]=roster;teams.addWidget(card,1)
        body.addLayout(teams);body.addStretch()
        scroll.viewport().installEventFilter(self)

    def eventFilter(self,watched,event):
        scroll=getattr(self,'battle_scroll',None)
        if scroll is not None and watched is scroll.viewport() and event.type()==QEvent.Type.Resize:
            self.reflow_battle_cards(event.size().width())
        return super().eventFilter(watched,event)

    def reflow_battle_cards(self,width=None):
        width=self.battle_scroll.viewport().width() if width is None else width
        team_width=max(0,(width-self.teams_layout.spacing())//2)
        for roster in self.team_layouts.values():
            for i in range(roster.count()):
                card=roster.itemAt(i).widget()
                if hasattr(card,'fit_width'):card.fit_width(team_width)

    def show_damage_calculator(self):
        from damage_calculator_widgets import DamageCalculatorDialog
        old=getattr(self,'calculator_dialog',None)
        if old is not None:
            try:
                if old.isVisible():old.raise_();old.activateWindow();return
            except RuntimeError:pass  # previous WA_DeleteOnClose dialog
        self.calculator_dialog=DamageCalculatorDialog(self,self.latest)
        self.calculator_dialog.show()

    def show_record_info(self):
        d=Editor(self,'本场记录信息');d.save.hide()
        d.form.addRow(label(self.record_info.text() or '暂无已保存对局'))
        d.form.addRow(label(self.capture_info.text()))
        d.actions.insertWidget(1,self.action('对应昵称',self.assign_nicknames));d.exec()

    def show_capture_storage(self):
        d=Editor(self,'监听缓存与本地保存');d.save.hide()
        d.form.addRow(label('内存：连接、会话、回放、玩家证据各最多64项；参与者别名最多512项。界面待处理事件最多128条，库存与计数等状态合并为最新一份。停止后释放解析缓存。'))
        d.form.addRow(label('磁盘：历史对局和库存快照保存在本机数据库，不自动删除。运行日志每份2MB，保留当前及3份旧日志。持续监听不另存完整原始抓包。'))
        d.form.addRow(label('清理历史请使用“历史与日志”的多选删除；需要保留资料时先备份数据库。删除可恢复，不会立即缩小数据库文件。'))
        d.actions.insertWidget(1,self.action('打开数据目录',self.open_directory));d.actions.insertWidget(1,self.action('备份数据库',self.backup));d.exec()

    def assign_nicknames(self):
        if not self.current_id:self.notify('请先选择一场对局');return
        bid=self.current_id;ctx=self.archive.context(bid);d=Editor(self,'对应双方昵称')
        names=list(dict.fromkeys(p['nickname'] for p in ctx.get('participants',[])))
        boxes={}
        for team in ('A','B'):
            box=QComboBox();box.addItem('未对应',None)
            for name in names:box.addItem(name,name)
            box.setCurrentIndex(max(0,box.findData(ctx.get('team_names',{}).get(team))))
            boxes[team]=box;d.form.addRow(team+' 方',box)
        d.form.addRow(label('昵称已读取，但当前记录缺少可靠方向证据。请按阵容选择一次，对应关系仅保存在本场。没有昵称时可到“校正”填写。','hint'))
        def save():
            selected={t:box.currentData() for t,box in boxes.items() if box.currentData()}
            if len(selected)==2 and selected['A']==selected['B']:raise ValueError('同一个昵称不能同时分配到双方')
            review=ctx.get('review',{})
            self.archive.set_review(bid,review.get('winner'),review.get('own_replay',False),selected);self.render_battle();self.refresh_history()
        d.on_save=save;d.exec()
    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().hide(); item.widget().deleteLater()
    def render_battle(self):
        self._battle_dirty=False
        self.latest=None;ctx={}
        self.record_info.setText('')
        if self.current_id and not self.archive.is_deleted(self.current_id):
            record=self.archive.get(self.current_id); self.latest=copy.deepcopy(record['original']); self.latest['status']=record['status']
            self.latest['tracking']=record.get('tracking') or self.latest.get('tracking')
            for team,units in self.latest['teams'].items():
                for i,u in enumerate(units):
                    key=unit_key(team,i,u); units[i]=project_unit(u,self.mappings,record['annotations'].get(key)); units[i]['annotation_key']=key
            ctx=self.archive.context(self.current_id)
            self.latest['participants']=ctx.get('participants',[])
            self.latest['view_context']='replay' if ctx['sample_kind']=='回放/观战' else 'live'
            replay=self.latest['view_context']=='replay'
            result_label=result_text(ctx)
            winner=ctx.get('protocol_winner') if replay else ctx.get('winner')
            compact=result_label if result_label in ('胜利','失败','平局') else (f'{winner} 方胜' if winner in ('A','B') else '平局' if winner=='draw' else '结果未确认')
            if replay:compact+=' · 观战'
            self.battle_info.setText(compact);self.battle_info.setToolTip(result_label+' · '+ctx['sample_kind']+' · '+ctx['side_reason'])
            source='本场已校正' if ctx['result_origin']=='manual_review' else '根据本场结算积分自动判定' if ctx['result_origin']=='rating_change' else '结算含义待核对' if ctx['result_origin']=='unverified_code' else '历史手动标注' if ctx['result_origin']=='manual' else '尚无确认结果'
            self.record_info.setText(result_label+' · '+('回放记录 · 不计本人战绩 · ' if replay else '')+record['status']+' · '+source)
            names=[(p.get('team')+' 方：' if p.get('team') else '方向待确认：')+p['nickname'] for p in self.latest.get('participants',[])]
            if names:self.record_info.setText(self.record_info.text()+' · '+' / '.join(names))
            else:self.record_info.setText(self.record_info.text()+' · 昵称未采集，可在对局分类补填')
        elif self.unsaved_battle:
            self.latest=copy.deepcopy(self.unsaved_battle)
            self.battle_info.setText('自动保存失败 · 当前数据仍可导出，请检查磁盘和运行日志')
        else:self.current_id=None; self.battle_info.setText('等待对局')
        self.refresh_battle_navigation()
        for team,layout in self.team_layouts.items():
            replay=bool(self.latest and self.latest.get('view_context',self.latest.get('capture_context'))=='replay')
            own=ctx.get('own_team')
            heading=f'记录 {team} 方' if replay or not own else f'⚔  {"己方" if team==own else "敌方"}队伍 · {team} 方'
            nickname=ctx.get('team_names',{}).get(team)
            self.team_titles[team].setText((nickname+' · '+('己方' if team==own else '敌方') if own and not replay else nickname) if nickname else heading)
            self.team_titles[team].setToolTip(heading+(' · '+nickname if nickname else ''))
            self.nickname_buttons[team].setVisible(bool(self.latest and not nickname))
            title=self.team_titles[team]
            style='teamNeutral' if replay or not own else 'ownTeam' if team==own else 'enemyTeam'
            if title.objectName()!=style:
                title.setObjectName(style);title.style().unpolish(title);title.style().polish(title)
            winner=ctx.get('protocol_winner') if replay else ctx.get('winner')
            result='win' if winner==team else 'loss' if winner in ('A','B') else 'draw' if winner=='draw' else 'unknown'
            outcome=self.team_outcomes[team];outcome.setText({'win':'胜','loss':'负','draw':'平','unknown':'待确认'}[result])
            outcome.setProperty('result',result);outcome.style().unpolish(outcome);outcome.style().polish(outcome)
            outcome.setToolTip('本场已确认结果；未确认不会默认判胜负。')
            self.clear_layout(layout)
            units=self.latest['teams'].get(team,[]) if self.latest else []
            if not units:layout.addWidget(label('暂无角色数据\n开始监听后，进入战斗将自动更新。','hint'))
            for unit in units:
                layout.addWidget(unit_card(unit,team,self.action,self.edit_hero,self.edit_loadout,self.details))
        self.reflow_battle_cards()
    def refresh_battle_navigation(self):
        rows=self.archive.history_navigation(self.history_filter.currentData(),self.history_query); self.battle_navigation=[r['id'] for r in rows]
        self.battle_jump.blockSignals(True)
        signature=tuple((r['id'],r['capture_time'],r['sample_kind']) for r in rows)
        if signature!=getattr(self,'_navigation_signature',None):
            self._navigation_signature=signature;self.battle_jump.clear();self.battle_jump.setPlaceholderText('选择已保存对局')
            for row in rows:
                text=f"{stamp(row['capture_time'])} · {row['sample_kind']}"
                self.battle_jump.addItem(text,row['id'])
        index=self.battle_jump.findData(self.current_id); self.battle_jump.setCurrentIndex(index); self.battle_jump.blockSignals(False)
        self.previous_battle.setEnabled(index>=0 and index<len(rows)-1)
        self.next_battle.setEnabled(index>0)
        self.battle_position.setText(f'{len(rows)-index}/{len(rows)}' if index>=0 else str(len(rows)))

    def browse_battle(self, bid):
        if bid and not self.archive.is_deleted(bid):
            self.current_id=bid; self.browsing=True; self.render_battle(); self.navigate(0)

    def step_battle(self, direction):
        # Refresh to skip records removed since this view was opened.
        ids=[r['id'] for r in self.archive.history_navigation(self.history_filter.currentData(),self.history_query)]
        if self.current_id not in ids:return
        index=ids.index(self.current_id)+direction
        if 0<=index<len(ids):self.browse_battle(ids[index])

    def jump_battle(self):
        bid=self.battle_jump.currentData()
        if bid and bid!=self.current_id:self.browse_battle(bid)

    def back_to_history(self):
        if self.current_id and self.current_id not in [r['id'] for r in self.archive.history_navigation(self.history_filter.currentData(),self.history_query)]:
            self.history_query='';self.history_search.clear()
            self.history_filter.setCurrentIndex(0)
        ids=[r['id'] for r in self.archive.history_navigation(self.history_filter.currentData(),self.history_query)]
        if self.current_id in ids:self.history_offset=(ids.index(self.current_id)//100)*100
        self.navigate(3)
        if self.current_id in self.history_ids:
            row=self.history_ids.index(self.current_id); self.history_table.selectRow(row)
            self.history_table.scrollToItem(self.history_table.item(row,0))

    def show_capture_diagnostics(self):
        if not self.capture_diagnostics:self.notify('先开始监听或导入抓包，再查看读取诊断'); return
        d=Editor(self,'读取诊断 · 消息统计与阵容候选'); d.resize(800,650); d.save.hide()
        d.form.addRow(label('未知消息只保存编号和数量；阵容候选尚未确认消息含义，不计入战绩。','hint'))
        text=QPlainTextEdit(json.dumps(self.capture_diagnostics,ensure_ascii=False,indent=2)); text.setReadOnly(True); text.setMinimumHeight(380); d.form.addRow(text)
        timer=QTimer(d);timer.timeout.connect(lambda:text.setPlainText(json.dumps(self.capture_diagnostics,ensure_ascii=False,indent=2)));timer.start(1000)
        d.actions.insertWidget(1,self.action('确认模式候选',self.confirm_mode_candidate)); d.actions.insertWidget(1,self.action('导出读取诊断',lambda:self.write_json(self.capture_diagnostics,'etheria_capture_diagnostics.json'))); d.exec()

    def confirm_mode_candidate(self):
        candidates=self.capture_diagnostics.get('mode_candidates',[])
        if not candidates:self.notify('尚无模式字段候选；请从进入对局前开始抓包。当前JSON没有模式原值。'); return
        d=Editor(self,'确认模式编号 · 仅在多场对照一致后填写')
        candidate=combo([f"{c['opcode']} {c['path']} = {c['value']}" for c in candidates]); kind=combo(['BP排位','竞技场','练习/测试','撤销该编号映射'])
        d.form.addRow('开场候选',candidate); d.form.addRow('确认的类型',kind)
        d.form.addRow(label('候选是小整数，并不代表一定是模式。请先用同模式两场及其他模式一场对照；同一候选映射会应用到后续及已有记录。','hint'))
        def save():
            if kind.currentText()=='撤销该编号映射':self.archive.remove_mode_mapping(candidates[candidate.currentIndex()])
            else:self.archive.set_mode_mapping(candidates[candidate.currentIndex()],kind.currentText())
            self.mappings=self.archive.mappings(load_mappings())
            if self.job and self.job.thread.is_alive():self.job.engine.mappings=self.mappings
            self.refresh_all()
        d.on_save=save;d.exec()

    def render_capture_diagnostics(self, data):
        data=copy.deepcopy(data)
        bid=data.get('latest_record_id')
        if bid:
            try:
                ctx=self.archive.context(bid)
                data['local_projection']={key:ctx.get(key) for key in ('sample_kind','mode_origin','mode_reason','own_team','side_origin','side_reason','protocol_winner')}
                data['local_projection']['result']=result_text(ctx)
            except ValueError:pass
        self.capture_diagnostics=data; counts=data.get('counts',{}); context='回放/观战' if data.get('capture_context')=='replay' else '本人对局'
        prefix=f"监听场景：{context} · 下行 {counts.get('game_packets',0)} 分组 · {counts.get('messages',0)} 消息 · 开场 {counts.get('battles',0)} · 回放 {counts.get('replays',0)}"
        if counts.get('invalid_replays'):reason=f"回放解析失败 {counts['invalid_replays']} 次，请导出诊断并保留本地抓包"
        elif counts.get('invalid_openings'):reason=f"开场解析失败 {counts['invalid_openings']} 次，请导出诊断并保留本地抓包"
        elif data.get('lineup_candidates'):reason=f"发现 {len(data['lineup_candidates'])} 条阵容候选，请查看读取诊断"
        elif counts.get('replays'):reason='已读取回放阵容；回放不计本人战绩，胜负与回合过程未确认'
        elif counts.get('battles'):reason=f"已关联结算 {counts.get('linked_settlements',0)} 次 · 未关联 {counts.get('unlinked_settlements',0)+counts.get('ambiguous_settlements',0)} 次"
        elif counts.get('messages'):reason='已收到游戏消息，尚未识别开场；请在进入对局/回放之前开始监听'
        elif counts.get('game_packets') and counts.get('framing_discarded_bytes'):
            reason='已收到指定端口下行数据，但消息边界未同步；请查看诊断并保留抓包'
        else:reason='尚未识别游戏消息，请检查网卡、端口与开始监听的时间'
        self.capture_info.setText(prefix+' · '+reason)

    def edit_hero(self,u):
        d=Editor(self,f"角色编号 {u['hero_id']} · 名称映射"); entry=QLineEdit(u['hero_name']); d.form.addRow('名称',entry)
        d.form.addRow(label('只修改这个精确编号；皮肤编号独立保存，历史显示同步更新。','hint'))
        def save():self.archive.set_mapping('heroes',u['hero_id'],entry.text()); self.mapping_changed()
        d.on_save=save; d.exec()
    def edit_loadout(self,u):
        if not self.current_id:return
        bid=self.current_id; key=u['annotation_key']; a=u.get('manual') or {}; d=Editor(self,u['hero_name']+' · 本场配装修正')
        enabled=QCheckBox('使用手动智壳'); enabled.setChecked(a.get('shell') is not None)
        shell=QLineEdit(a.get('shell') or ''); shell.textEdited.connect(lambda _:enabled.setChecked(True))
        matrices_enabled=QCheckBox('使用手动矩阵（留空表示无）'); matrices_enabled.setChecked(a.get('matrices') is not None)
        matrices=QPlainTextEdit('\n'.join(f"{m['name']},{m['points']}" for m in a.get('matrices') or [])); matrices.setPlaceholderText('每行：狂怒,9'); matrices.setMinimumHeight(110)
        matrices.textChanged.connect(lambda:matrices_enabled.setChecked(True)); note=QPlainTextEdit(a.get('note','')); note.setMaximumHeight(85)
        d.form.addRow(enabled); d.form.addRow('智壳名称',shell); d.form.addRow(matrices_enabled); d.form.addRow('矩阵 / 点数',matrices); d.form.addRow('备注',note)
        def save():
            self.archive.annotate(bid,key,shell.text() if enabled.isChecked() else None,parse_matrices(matrices.toPlainText()) if matrices_enabled.isChecked() else None,note.toPlainText()); self.render_battle()
        def clear():self.archive.clear_annotation(bid,key); self.render_battle(); d.accept()
        d.on_save=save; d.actions.insertWidget(1,self.action('清除本场修正',clear)); d.exec()
    def details(self,u):
        d=Editor(self,u['hero_name']+' · 原始数据'); d.save.hide()
        totals=QPlainTextEdit(extra_text(u));totals.setReadOnly(True);totals.setMinimumHeight(180)
        d.form.addRow('开场增伤 / 减伤',totals)
        pending=QPlainTextEdit(pending_text(u));pending.setReadOnly(True);pending.setMinimumHeight(140)
        d.form.addRow('额外属性对照',pending)
        text=QPlainTextEdit(json.dumps(u,ensure_ascii=False,indent=2)); text.setReadOnly(True); text.setMinimumHeight(240); d.form.addRow(text)
        candidates=shell_candidates(u,self.mappings)
        for effect in candidates:d.form.addRow(self.action(f'命名智壳效果 #{effect}',lambda e=effect:self.edit_mapping('shell_effects',str(e))))
        d.exec()
    def edit_context(self,bid=None):
        bid=bid or self.current_id
        if not bid: self.notify('请先选择一场已保存对局'); return
        ctx=self.archive.context(bid); d=Editor(self,'对局分类与结果校正')
        code=ctx.get('result_code')
        d.form.addRow('原始结算',label(f'代码 {code}（代码不直接等于A/B胜方）' if code is not None else '未读取到可用结算'))
        side=combo(['自动识别 / 待确认','A 方是我','B 方是我'])
        if ctx['side_origin']=='manual':side.setCurrentIndex(1 if ctx['own_team']=='A' else 2)
        d.form.addRow('己方身份',side)
        own_replay=QCheckBox('这是我本人的对局／回放，计入所选分类')
        own_replay.setChecked(ctx.get('personal_confirmed',False));d.form.addRow(own_replay)
        remember=QCheckBox('记住所选玩家为本号，后续按身份自动判断方向')
        def enable_identity():
            valid=side.isEnabled() and side.currentIndex()>0 and [None,'A','B'][side.currentIndex()] in ctx.get('remember_identity_teams',[])
            remember.setEnabled(valid)
            if not valid:remember.setChecked(False)
        def enable_side():
            side.setEnabled(ctx['sample_kind']!='回放/观战' or own_replay.isChecked());enable_identity()
        side.currentIndexChanged.connect(enable_identity);own_replay.toggled.connect(enable_side);enable_side();d.form.addRow(remember)
        d.form.addRow(label(ctx['side_reason'],'hint'))
        kind=combo(KINDS,ctx['sample_kind']); group=QLineEdit(ctx['dataset_group'])
        d.form.addRow('对局类型',kind); d.form.addRow('分组 / 赛季',group)
        winner=QComboBox()
        for text,value in [('未确认／清除本场校正',None),('A 方获胜','A'),('B 方获胜','B'),('平局','draw'),('确认无法判断','unknown')]:winner.addItem(text,value)
        winner.setCurrentIndex(max(0,winner.findData(ctx.get('reviewed_winner'))));d.form.addRow('本场胜方',winner)
        nick_a=QLineEdit(ctx.get('team_names',{}).get('A',''));nick_b=QLineEdit(ctx.get('team_names',{}).get('B',''))
        nick_a.setPlaceholderText('未采集，可手动填写');nick_b.setPlaceholderText('未采集，可手动填写')
        d.form.addRow('A 方昵称',nick_a);d.form.addRow('B 方昵称',nick_b)
        d.form.addRow(label('本场校正独立保存，不改原始数据。自己的回放须选择己方和排位／竞技场等分类；没有胜负依据时保留未确认。','hint'))
        def save():
            own=[None,'A','B'][side.currentIndex()]
            if len(group.text().strip())>100:raise ValueError('统计分组最多100字')
            if own_replay.isChecked() and (own not in ('A','B') or kind.currentText() not in ('BP排位','竞技场','GVG','PVE','练习/测试')):raise ValueError('请先确认己方A/B，并选择本人对局分类')
            if remember.isChecked() and kind.currentText()=='回放/观战':raise ValueError('请先选择本人对局类型，再记住本号身份')
            self.archive.set_review(bid,winner.currentData(),own_replay.isChecked(),{'A':nick_a.text(),'B':nick_b.text()})
            self.archive.set_perspective(bid,own,remember.isChecked());self.archive.set_classification(bid,kind.currentText(),group.text());self.refresh_all()
        d.on_save=save; d.exec()
    def hero_name(self,identifier):return self.mappings['heroes'].get(str(identifier),f'角色 #{identifier}')
    def build_stats(self):
        layout=self.page(); layout.addWidget(label('本地观测样本 · 对位反映整队结果，不能视为单挑克制或全服胜率。','hint'))
        bar=QHBoxLayout(); self.stats_kind=combo(['BP排位','竞技场','GVG','PVE','全部已分类','未分类','练习/测试']); self.stats_group=QLineEdit(); self.stats_group.setPlaceholderText('分组 / 赛季（可留空）')
        self.stats_focus=combo(['全部角色']); self.stats_focus.setMinimumWidth(170); self.stats_perspective=combo(['仅己方','双方队伍']); self.stats_min=QSpinBox(); self.stats_min.setRange(1,100000); self.stats_min.setValue(5); self.stats_min.setPrefix('最少样本 ')
        for w in [self.stats_kind,self.stats_group,self.stats_focus,self.stats_perspective,self.stats_min]:bar.addWidget(w)
        bar.addWidget(self.action('刷新',self.refresh_stats)); layout.addLayout(bar)
        self.stats_summary=label('','hero'); layout.addWidget(self.stats_summary)
        tabs=QTabWidget(); self.stat_tables=[]
        for title,headers in [('角色概览',['角色','精确编号','出场','胜','负','平','未知','胜率样本','胜率']),('对位 · 低胜率优先',['角色','对方角色','胜','负','胜率样本','胜率']),('搭配 · 高胜率优先',['角色一','角色二','胜','负','胜率样本','胜率'])]:
            t=table(headers); tabs.addTab(t,title); self.stat_tables.append(t)
        layout.addWidget(tabs,1); row=QHBoxLayout(); row.addStretch(); row.addWidget(self.action('导出分析数据集',lambda:self.write_json(self.archive.dataset(),'etheria_analysis_dataset.json'))); layout.addLayout(row)
        for w in [self.stats_kind,self.stats_focus,self.stats_perspective]:w.currentIndexChanged.connect(lambda _:self.refresh_stats(False))
        self.stats_min.valueChanged.connect(lambda _:self.refresh_stats(False)); self.stats_group.returnPressed.connect(self.refresh_stats)
    def refresh_stats(self,force=True):
        if force:self._stats_dirty=True
        if self._stats_dirty or not hasattr(self,'_stats_dataset'):
            self._stats_dataset=self.archive.analysis_dataset();self._stats_dirty=False;self._stats_signature=None
        ds=self._stats_dataset;kinds=('BP排位','竞技场','GVG','PVE','练习/测试') if self.stats_kind.currentText()=='全部已分类' else (self.stats_kind.currentText(),)
        signature=(kinds,self.stats_group.text().strip(),self.stats_perspective.currentIndex())
        if signature!=self._stats_signature:
            self._stats_result=analyse(ds,self.mappings,kinds,signature[1],'own' if signature[2]==0 else 'both');self._stats_signature=signature
        result=self._stats_result
        focus=self.stats_focus.currentData(); self.stats_focus.blockSignals(True); self.stats_focus.clear(); self.stats_focus.addItem('全部角色',None)
        for hid in sorted({u['hero_id'] for b in ds['battles'] for units in b['original']['teams'].values() for u in units}):self.stats_focus.addItem(f'{self.hero_name(hid)}  #{hid}',hid)
        index=self.stats_focus.findData(focus); self.stats_focus.setCurrentIndex(max(index,0)); self.stats_focus.blockSignals(False); focus=self.stats_focus.currentData()
        self.stats_summary.setText(f"{result['eligible_matches']} 场对局   /   {result['decided_matches']} 场已知胜负   /   {result['team_samples']} 份队伍样本")
        fill(self.stat_tables[0],[[r['hero_name'],r['hero_id'],r['appearances'],r['wins'],r['losses'],r['draws'],r['unknown'],r['decided'],percent(r['win_rate'])] for r in result['heroes'] if focus is None or r['hero_id']==focus])
        for category,t in [('matchups',self.stat_tables[1]),('cooccurrences',self.stat_tables[2])]:
            ranked=rank_statistics(result,category,focus,self.stats_min.value()); rows=[]
            for r in ranked:
                ids=[r['hero_id'],r['opponent_id']] if category=='matchups' else r['hero_ids']
                rows.append([*[self.hero_name(i) for i in ids],r['wins'],r['losses'],r['decided'],percent(r['win_rate'])])
            fill(t,rows)
    def build_inventory(self):
        layout=self.page(); self.bag_info=label('','hint'); layout.addWidget(self.bag_info)
        bar=QHBoxLayout(); self.gear_query=QLineEdit(); self.gear_query.setPlaceholderText('搜索矩阵 / 角色 / 源器或元件编号'); self.gear_query.textChanged.connect(lambda _:self.render_inventory()); bar.addWidget(self.gear_query,1)
        bar.addWidget(self.action('分类筛选',self.edit_gear_filters,True))
        bar.addWidget(self.action('清除筛选',self.clear_gear_filters))
        bar.addWidget(self.action('校正分类',self.edit_gear_metadata))
        bar.addWidget(self.action('导出库存',lambda:self.write_json(self.bag_snapshot,'etheria_local_inventory.json'))); layout.addLayout(bar)
        sorting=QHBoxLayout(); sorting.addWidget(label('排序'))
        self.gear_sort_key=QComboBox(); self.gear_sort_key.addItem('默认顺序','default'); self.gear_sort_key.addItem('等级','level')
        for tag,spec in ATTRIBUTES.items():self.gear_sort_key.addItem(spec[0],f'attr:{tag}')
        self.gear_sort_key.setCurrentIndex(self.gear_sort_key.findData(self.gear_sort['key']))
        self.gear_sort_scope=QComboBox()
        for text,key in [('副属性','subs'),('主属性','main'),('主副属性合计','all')]:self.gear_sort_scope.addItem(text,key)
        self.gear_sort_scope.setCurrentIndex(self.gear_sort_scope.findData(self.gear_sort['scope']))
        self.gear_sort_order=combo(['从高到低','从低到高'],'从高到低' if self.gear_sort['descending'] else '从低到高')
        for w in (self.gear_sort_key,self.gear_sort_scope,self.gear_sort_order):sorting.addWidget(w); w.currentIndexChanged.connect(self.change_gear_sort)
        sorting.addStretch(); sorting.addWidget(label('按解码小数值排序 · 缺少该属性的源器排在末尾','hint')); layout.addLayout(sorting)
        self.gear_filter_info=label('','hint'); layout.addWidget(self.gear_filter_info)
        tabs=QTabWidget(); self.inventory_tabs=tabs; self.gear_table=table(['源器编号','等级','排序数值','矩阵','点数','稀有度','初始副属性','主属性','副属性','装备关联']); self.loadout_table=table(['角色','精确编号','配装类型','智壳','矩阵'])
        tabs.addTab(self.gear_table,'源器背包'); tabs.addTab(self.loadout_table,'本号智壳与矩阵'); layout.addWidget(tabs,1)
        self.component_table=table(['元件编号','名称 / 配置','基础主属性','基础副属性','专属刻影','装配引用','锁定标志'])
        tabs.addTab(self.component_table,'元件背包')
        self.gear_details=QPlainTextEdit(); self.gear_details.setReadOnly(True); self.gear_details.setMaximumHeight(180); layout.addWidget(self.gear_details)
        self.gear_table.itemSelectionChanged.connect(self.gear_detail)
        self.component_table.itemSelectionChanged.connect(self.component_detail)
        tabs.currentChanged.connect(lambda _:self.component_detail() if tabs.currentWidget()==self.component_table else self.gear_detail())
        self.gear_table.cellDoubleClicked.connect(lambda r,c:self.edit_gear_metadata())
    def change_gear_sort(self):
        self.gear_sort=normalize_sort({'key':self.gear_sort_key.currentData(),'scope':self.gear_sort_scope.currentData(),
                                       'descending':self.gear_sort_order.currentIndex()==0})
        self.archive.save_settings({'gear_sort':self.gear_sort}); self.render_inventory()
    def edit_gear_filters(self):
        options=filter_options(self.mappings,(self.bag_snapshot or {}).get('gear',[]))
        dialog=GearFilterDialog(options,self.gear_filters,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.gear_filters=dialog.selected(); self.archive.save_settings({'gear_filters':self.gear_filters}); self.render_inventory()
    def clear_gear_filters(self):
        self.gear_filters=normalize_filters({}); self.archive.save_settings({'gear_filters':self.gear_filters})
        self.gear_query.clear(); self.render_inventory()
    def edit_gear_metadata(self):
        row=self.gear_table.currentRow()
        if not 0<=row<len(self.gear_display):self.notify('请先选择一件源器'); return
        gear=self.gear_display[row]; p=project_gear(gear,self.gear_metadata.get(gear['uid']))
        d=Editor(self,'校正源器分类 · '+str(gear['uid']))
        rarity=combo(['未知',*RARITIES],p['rarity'] if p['rarity']!=UNKNOWN else '未知')
        initial=combo(['未知','0','1','2','3','4'],str(p['initial']) if p['initial']!=UNKNOWN else '未知')
        d.form.addRow('稀有度',rarity); d.form.addRow('初始副属性条数',initial)
        d.form.addRow(label('只影响这件源器的分类，强化更新不会覆盖手工记录。初始条数不等于当前条数；不清楚时保留未知。','hint'))
        def save():
            value={'rarity':rarity.currentText() if rarity.currentText()!='未知' else UNKNOWN,
                   'initial_sub_count':int(initial.currentText()) if initial.currentText()!='未知' else UNKNOWN}
            self.archive.set_gear_metadata(gear['uid'],value); self.gear_metadata=self.archive.gear_metadata(); self.render_inventory()
        d.on_save=save; d.exec()
    def render_inventory(self):
        self._inventory_dirty=False
        snap=self.bag_snapshot or {}; query=self.gear_query.text().strip().lower(); holders={}
        oldrow=self.gear_table.currentRow()
        selected=self.gear_display[oldrow]['uid'] if hasattr(self,'gear_display') and 0<=oldrow<len(self.gear_display) else None
        for hero in snap.get('heroes',[]):
            for field,title in [('normal_gear_uids','普通'),('arena_gear_uids','竞技候选')]:
                for uid in hero.get(field,[]):holders.setdefault(uid,[]).append(self.hero_name(hero['hero_id'])+'·'+title)
        rows=[]; self.gear_display=[]
        attr_sort=self.gear_sort['key'].startswith('attr:')
        self.gear_sort_scope.setEnabled(attr_sort)
        self.gear_sort_order.setEnabled(self.gear_sort['key']!='default')
        self.gear_table.setColumnHidden(2,self.gear_sort['key']=='default')
        self.gear_table.horizontalHeaderItem(2).setText(self.gear_sort_key.currentText()+' · 排序值')
        for gear in sort_gear(snap.get('gear',[]),self.gear_sort):
            metadata=self.gear_metadata.get(gear['uid'])
            if not matches_gear(gear,self.gear_filters,metadata):continue
            p=project_gear(gear,metadata); matrix=gear.get('matrix') or {}
            sort_value=gear_sort_value(gear,self.gear_sort)
            suffix=ATTRIBUTES[int(self.gear_sort['key'].split(':')[1])][2] if attr_sort else ''
            values=[gear['uid'],gear.get('level') if gear.get('level') is not None else '未知',
                    f'{sort_value:g}{suffix}' if sort_value is not None else '—',
                    matrix_name(self.mappings,matrix['id']) if matrix.get('id') is not None else '未知',
                    matrix.get('points') if matrix.get('points') is not None else '未知',
                    p['rarity'] if p['rarity']!=UNKNOWN else '未知',p['initial'] if p['initial']!=UNKNOWN else '未知',
                    attribute_text(p['main']) if p['main'] else '未知',
                    ' / '.join(attribute_text(a) for a in p['subs']) or '未知',
                    ' / '.join(holders.get(gear['uid'],[])) or '无已观测关联']
            if query and query not in (' '.join(map(str,values))+' '+str(gear['config_id'])).lower():continue
            rows.append(values); self.gear_display.append(gear)
        self.gear_table.blockSignals(True); fill(self.gear_table,rows); self.gear_table.clearSelection(); self.gear_table.setCurrentCell(-1,-1)
        for i,g in enumerate(self.gear_display):
            if g['uid']==selected:self.gear_table.selectRow(i); break
        self.gear_table.blockSignals(False); loads=[]
        for r in self.inventory_rows:
            values=[self.hero_name(r['hero_id']),r['hero_id'],r['mode'],shell_config_name(self.mappings,r['shell_config_id']),' / '.join(f"{matrix_name(self.mappings,m['id'])} +{m['points']}" for m in r['matrices'])+('（数据不全）' if r['incomplete'] else '')]
            if not query or query in ' '.join(map(str,values)).lower():loads.append(values)
        fill(self.loadout_table,loads)
        old_component_row=self.component_table.currentRow()
        selected_component=self.component_display[old_component_row]['uid'] if hasattr(self,'component_display') and 0<=old_component_row<len(self.component_display) else None
        component_rows=[];self.component_display=[]
        for item in snap.get('components',[]):
            projection=project_component(item,snap.get('component_groups',[]),self.mappings)
            attributes=projection['attributes']
            values=[item['uid'],f"{projection['name']} / {item.get('config_id_raw','—')}",
                    component_attribute_text(attributes[0]) if attributes else '未知',
                    ' / '.join(component_attribute_text(a) for a in attributes[1:]) or '未知',
                    projection['exclusive'],
                    ' / '.join(f"{h['name']} · 槽{h['slot']}"+(' · 专属+20%' if h['bonus_active'] else '') for h in projection['holders']) or '无已观测引用',
                    projection['lock']]
            if query and query not in ' '.join(map(str,values)).lower():continue
            component_rows.append(values);self.component_display.append(item)
        self.component_table.blockSignals(True);fill(self.component_table,component_rows)
        self.component_table.clearSelection();self.component_table.setCurrentCell(-1,-1)
        for i,item in enumerate(self.component_display):
            if item['uid']==selected_component:self.component_table.selectRow(i);break
        self.component_table.blockSignals(False)
        component_count=f"{len(snap['components'])} 件" if 'components' in snap else '未采集'
        component_time=f" · 元件观测 {stamp(snap.get('components_capture_time'))}" if 'components' in snap else ''
        self.bag_info.setText(f"筛出 {len(rows)} / {len(snap.get('gear',[]))} 件源器 · 智壳 {len(snap.get('shells',[]))} 个 · 元件 {component_count} · 采集 {stamp(snap.get('capture_time'))}"+component_time)
        self.gear_filter_info.setText(filter_summary(self.gear_filters,filter_options(self.mappings,snap.get('gear',[]))))
        self.gear_details.setPlainText('点击源器查看属性与原值。主副属性按已对照规则解码；未确认字段显示未知。稀有度和初始副属性条数可通过“校正分类”记录。')
        if self.inventory_tabs.currentWidget()==self.component_table:self.component_detail()
        else:self.gear_detail()
    def component_detail(self):
        row=self.component_table.currentRow()
        if not hasattr(self,'component_display') or not 0<=row<len(self.component_display):
            self.gear_details.setPlainText('元件仅记录登录快照。表格显示基础值，选择元件查看对应刻影装配后的数值与原始记录；未知编号保留待确认。源器分类和属性排序不作用于元件。');return
        item=self.component_display[row]
        projection=project_component(item,(self.bag_snapshot or {}).get('component_groups',[]),self.mappings)
        self.gear_details.setPlainText(component_detail_text(item,projection))
    def gear_detail(self):
        row=self.gear_table.currentRow()
        if 0<=row<len(self.gear_display):
            gear=self.gear_display[row]; p=project_gear(gear,self.gear_metadata.get(gear['uid']))
            text='\n'.join(('主属性：' if i==0 else '副属性：')+attribute_text(a)+
                           (f" · 追加次数 {a['upgrade_count_tentative']}（观测推定）" if i else '') for i,a in enumerate(p['attributes']))
            self.gear_details.setPlainText(text+'\n\n原始记录：\n'+json.dumps(gear,ensure_ascii=False,indent=2))
    def build_history(self):
        layout=self.page(); row=QHBoxLayout(); self.history_info=label('','hint'); row.addWidget(self.history_info,1)
        self.history_filter=QComboBox();self.history_filter.addItem('全部类型',None)
        for name in KINDS:self.history_filter.addItem(name,name)
        row.addWidget(self.history_filter);self.history_filter.currentIndexChanged.connect(self.change_history_filter)
        for text,fn in [('上一页',lambda:self.history_page(-1)),('下一页',lambda:self.history_page(1)),('打开',self.open_history),('删除选中',self.delete_history),('恢复最近删除',self.restore_history)]:row.addWidget(self.action(text,fn))
        layout.addLayout(row)
        search=QHBoxLayout();self.history_search=QLineEdit();self.history_search.setPlaceholderText('查找玩家昵称（支持部分名字或完整#编号）')
        search.addWidget(self.history_search,1);search.addWidget(self.action('查找战绩',self.apply_history_search));search.addWidget(self.action('清除查找',self.clear_history_search));layout.addLayout(search)
        self.history_search.returnPressed.connect(self.apply_history_search)
        self.history_search_info=label('','hint');layout.addWidget(self.history_search_info)
        self.history_table=table(['时间','来源','状态','双方昵称','类型','结果']); layout.addWidget(self.history_table,1)
        self.history_table.cellDoubleClicked.connect(lambda r,c:self.open_history());delete_shortcut(self.history_table,self.delete_history)
        row=QHBoxLayout()
        for text,fn in [('修改对局分类',self.context_selected),('导出分析数据集',lambda:self.write_json(self.archive.dataset(),'etheria_analysis_dataset.json')),('打开日志目录',self.open_directory),('备份数据库',self.backup),('查看结算观测',self.observations)]:row.addWidget(self.action(text,fn))
        layout.addLayout(row)
        actions=QHBoxLayout();actions.addWidget(self.action('批量分类选中',self.classify_selected));actions.addWidget(self.action('删除当前筛选全部记录',self.delete_filtered_history));actions.addStretch();layout.addLayout(actions)
        layout.addWidget(label('Ctrl+左键 / Shift 多选后按 Delete；Ctrl+A 选择当前页。“删除当前筛选全部记录”包括后续页，可恢复最近一批。昵称战绩仅统计已确认己方与胜负。','hint'))
    def apply_history_search(self):
        self.history_query=self.history_search.text().strip();self.change_history_filter()
    def clear_history_search(self):
        self.history_search.clear();self.apply_history_search()
    def change_history_filter(self):
        self.history_offset=0;self._history_search_dirty=True; self.refresh_history(); self.refresh_battle_navigation()

    def refresh_history(self):
        selected=set(self.selected_ids()) if self.history_ids else set()
        total,records=self.archive.history(100,self.history_offset,self.history_filter.currentData(),self.history_query)
        if not records and self.history_offset and total:self.history_offset=max(0,((total-1)//100)*100); total,records=self.archive.history(100,self.history_offset,self.history_filter.currentData(),self.history_query)
        self.history_ids=[r['id'] for r in records]; rows=[]
        for r in records:
            rows.append([stamp(r['capture_time']),r['source'],r['status'],' / '.join(p['nickname'] for p in r['participants']) or '未采集昵称',r['sample_kind'],result_text(r)])
        fill(self.history_table,rows)
        selection=self.history_table.selectionModel();selection.clearSelection()
        from PySide6.QtCore import QItemSelectionModel
        for i,bid in enumerate(self.history_ids):
            if bid in selected:selection.select(self.history_table.model().index(i,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        self.history_info.setText(f'{total} 场记录 · 第 {self.history_offset//100+1} 页')
        if self._history_search_dirty:
            if self.history_query:
                result=self.archive.search_results(self.history_filter.currentData(),self.history_query)
                self.history_search_info.setText(f"查找“{self.history_query}”：{result['total']} 场 · 己方 {result['wins']} 胜 {result['losses']} 负 {result['draws']} 平 · {result['unknown']} 场未确认 · 胜率 {percent(result['win_rate'])}")
            else:self.history_search_info.setText('输入昵称后按回车，查看双方名单、相关对局与己方对战成绩。')
            self._history_search_dirty=False
    def history_page(self,direction):
        total,_=self.archive.history(0,sample_kind=self.history_filter.currentData(),query=self.history_query); offset=max(0,self.history_offset+direction*100)
        if offset>=total and direction>0:return
        self.history_offset=offset; self.refresh_history()
    def selected_ids(self):return [self.history_ids[i.row()] for i in self.history_table.selectionModel().selectedRows() if i.row()<len(self.history_ids)]
    def open_history(self):
        ids=self.selected_ids()
        if ids:self.browse_battle(ids[0])
    def context_selected(self):
        ids=self.selected_ids()
        if ids:self.edit_context(ids[0])
    def delete_history(self):
        ids=self.selected_ids()
        if not ids:self.notify('先选择记录，可按 Ctrl / Shift 多选'); return
        self.delete_battles(ids)
    def delete_filtered_history(self):
        if self.history_filter.currentData() is None and not self.history_query:
            self.notify('请先选择一个类型或查找昵称，再删除全部筛选结果');return
        self.delete_battles([r['id'] for r in self.archive.history_navigation(self.history_filter.currentData(),self.history_query)])
    def delete_battles(self,ids):
        removed=self.archive.trash_battles(ids)
        if self.current_id in removed:self.current_id=None; self.browsing=False
        if self.live_id in removed:self.live_id=None
        self.refresh_records(); self.notify(f'已删除 {len(removed)} 场，可恢复最近一批删除')
    def restore_history(self):
        restored=self.archive.restore_last_trash(); self.refresh_records(); self.notify(f'已恢复 {len(restored)} 场')
    def classify_selected(self):
        ids=self.selected_ids()
        if not ids:self.notify('先用 Ctrl / Shift 选择要分类的对局');return
        d=Editor(self,f'批量分类 · {len(ids)} 场');kind=combo(KINDS);d.form.addRow('类型',kind)
        d.form.addRow(label('选择“未分类”恢复自动分类；本场胜负、身份校正和统计分组保留。','hint'))
        def save():
            changed=self.archive.classify_battles(ids,kind.currentText());self.refresh_records();self.notify(f'已分类 {len(changed)} 场')
        d.on_save=save;d.exec()
    def return_live(self):
        self.browsing=False; self.current_id=self.live_id if self.live_id and not self.archive.is_deleted(self.live_id) else None; self.render_battle()
    def build_mappings(self):
        layout=self.page(); row=QHBoxLayout(); self.map_category=combo(list(CATEGORIES)); self.map_query=QLineEdit(); self.map_query.setPlaceholderText('搜索编号或名称'); row.addWidget(self.map_category); row.addWidget(self.map_query,1)
        layout.addLayout(row)
        actions=QHBoxLayout()
        actions.addWidget(self.action('新增',self.new_mapping)); actions.addWidget(self.action('编辑选中',self.edit_selected_mapping))
        actions.addWidget(self.action('删除自定义',self.restore_mapping))
        self.undo_mapping_btn=self.action('撤销删除',self.undo_mapping_delete); actions.addWidget(self.undo_mapping_btn)
        actions.addWidget(self.action('智壳候选编号清单',self.shell_catalogue)); actions.addStretch(); layout.addLayout(actions)
        self.mapping_table=table(['编号','名称','效果档位','来源']); layout.addWidget(self.mapping_table,1)
        delete_shortcut(self.mapping_table,self.restore_mapping)
        self.mapping_table.cellDoubleClicked.connect(lambda r,c:self.edit_selected_mapping()); self.map_category.currentIndexChanged.connect(lambda _:self.render_mappings()); self.map_query.textChanged.connect(lambda _:self.render_mappings())
        layout.addWidget(label('按 Ctrl / Shift 可多选删除自定义映射。有内置对应时恢复内置名称；纯自定义编号会移除。可撤销本次会话最近一批删除，原始数据保留。','hint'))
    def render_mappings(self):
        category=CATEGORIES[self.map_category.currentText()]; custom=self.archive.custom_mappings(category); rows=[]; query=self.map_query.text().strip().lower()
        for identifier,value in sorted(self.mappings[category].items(),key=lambda x:int(x[0])):
            threshold=value.get('threshold') if isinstance(value,dict) else None
            shown_threshold=threshold if threshold is not None else '待确认' if category=='matrix_effects' else ''
            row=[identifier,value.get('name','') if isinstance(value,dict) else value,shown_threshold, '用户映射' if identifier in custom else '内置']
            if not query or query in ' '.join(map(str,row)).lower():rows.append(row)
        fill(self.mapping_table,rows)
        self.undo_mapping_btn.setEnabled(self._mapping_undo is not None)
    def new_mapping(self):
        self.edit_mapping(CATEGORIES[self.map_category.currentText()])
    def edit_selected_mapping(self):
        row=self.mapping_table.currentRow(); identifier=self.mapping_table.item(row,0).text() if row>=0 else ''
        if identifier:self.edit_mapping(CATEGORIES[self.map_category.currentText()],identifier)
        else:self.notify('请先选择要编辑的编号，新增请点击“新增”')
    def edit_mapping(self,category,identifier=''):
        value=self.mappings[category].get(identifier,''); d=Editor(self,'编号名称映射')
        code=QLineEdit(identifier); name=QLineEdit(value.get('name','') if isinstance(value,dict) else value); points=QSpinBox(); points.setRange(0,999); points.setSpecialValueText('待确认'); points.setValue((value.get('threshold') or 0) if isinstance(value,dict) else 0)
        d.form.addRow('编号',code); d.form.addRow('名称',name)
        if category=='matrix_effects':d.form.addRow('生效档位',points)
        def save():self.archive.set_mapping(category,code.text(),name.text(),points.value() or None); self.mapping_changed()
        d.on_save=save; d.exec()
    def restore_mapping(self):
        category=CATEGORIES[self.map_category.currentText()]
        identifiers=[self.mapping_table.item(index.row(),0).text() for index in self.mapping_table.selectionModel().selectedRows()]
        if not identifiers:self.notify('请先选择要删除的自定义映射');return
        removed=self.archive.remove_mappings(category,identifiers)
        if not removed:self.notify('所选均为内置映射，无自定义内容可删除');return
        self._mapping_undo=(category,removed)
        self.mapping_table.clearSelection(); self.mapping_changed()
        self.notify(f'已删除 {len(removed)} 项自定义映射，可撤销；内置名称自动恢复')
    def undo_mapping_delete(self):
        if self._mapping_undo is None:return
        category,values=self._mapping_undo
        restored=self.archive.restore_mappings(category,values)
        self._mapping_undo=None; self.mapping_changed()
        self.notify(f'已恢复 {len(restored)} 项；跳过 {len(values)-len(restored)} 项已有新自定义内容的编号')
    def mapping_changed(self):
        self.mappings=self.archive.mappings(load_mappings());self._stats_dirty=True;self._battle_dirty=True;self._inventory_dirty=True
        self.render_mappings()
        if self.stack.currentIndex()==0:self.render_battle()
        elif self.stack.currentIndex()==2:self.render_inventory()
    def shell_catalogue(self):
        d=Editor(self,'智壳候选编号 · 双击命名'); d.resize(850,600); d.save.hide(); t=table(['效果编号','名称','状态','对局数','角色']); rows=self.archive.shell_catalogue(self.mappings)
        fill(t,[[r['id'],r['name'],r['status'],r['battle_count'],' / '.join(r['heroes'])] for r in rows]); t.setMinimumHeight(330); d.form.addRow(t)
        def edit(r,c):self.edit_mapping('shell_effects',str(rows[r]['id'])); d.accept()
        t.cellDoubleClicked.connect(edit); d.exec()
    def build_settings(self):
        layout=self.page(); card,c=self.card(); form=QFormLayout(); c.addLayout(form); layout.addWidget(card); layout.addStretch()
        self.own_nickname=QLineEdit(self.preferences.get('own_nickname',''));self.own_nickname.setMaxLength(64)
        self.own_nickname.setPlaceholderText('推荐填写完整昵称，例如 玩家名#1234')
        form.addRow('我的游戏昵称',self.own_nickname)
        form.addRow(label('昵称用于识别己方，结算积分用于判断胜负。省略#数字时须本场唯一匹配；重名、缺数据或观战保持待确认。本场手动校正优先。','hint'))
        self.dumpcap=QLineEdit(self.preferences.get('dumpcap') or find_dumpcap()); line=QHBoxLayout(); line.addWidget(self.dumpcap,1); line.addWidget(self.action('浏览',self.browse_dumpcap)); form.addRow('dumpcap 路径',line)
        self.interface=QComboBox(); self.interface.setMinimumWidth(440); line=QHBoxLayout(); line.addWidget(self.interface,1); self.refresh_interfaces_btn=self.action('刷新网卡',self.refresh_interfaces); line.addWidget(self.refresh_interfaces_btn); form.addRow('监听网卡',line)
        self.port=QSpinBox(); self.port.setRange(1,65535)
        try:self.port.setValue(int(self.preferences.get('port',20001)))
        except (ValueError,TypeError):self.port.setValue(20001)
        form.addRow('游戏端口',self.port); self.topmost=QCheckBox('窗口置顶'); self.topmost.setChecked(bool(self.preferences.get('topmost',False))); form.addRow(self.topmost); self.topmost.toggled.connect(self.set_topmost)
        self.capture_scene=QComboBox(); self.capture_scene.addItem('本人对局','live'); self.capture_scene.addItem('他人回放 / 观战（不计本人战绩）','replay')
        self.capture_scene.setCurrentIndex(max(0,self.capture_scene.findData(self.preferences.get('capture_context','live')))); form.addRow('采集场景',self.capture_scene)
        form.addRow(label('0x8421回放自动识别；其他观战封装可手动指定场景。模式编号未确认时保留未分类。','hint'))
        form.addRow(label('在本人对局的“对局分类”中确认方向并勾选“记住所选玩家为本号”。需要读到玩家资料和可对应方向的选人记录；证据不足时仍需本场确认。','hint'))
        form.addRow(self.action('清除记住的本号身份',self.clear_player_identity))
        c.addWidget(self.action('保存设置',self.save_preferences,True)); c.addWidget(label('使用已安装的 Wireshark / dumpcap 和 Npcap。网卡刷新在后台执行，抓包只在你点击开始后运行。','hint'))
        helpbar=QHBoxLayout();helpbar.addWidget(self.action('抓包组件安装说明',self.capture_setup_help));helpbar.addWidget(self.action('重新检测 dumpcap',self.detect_dumpcap));helpbar.addStretch();c.addLayout(helpbar)
        c.addWidget(label('默认发布包复用已安装的抓包组件；Npcap需要单独安装。离线导入无需实时抓包驱动。','hint'))
        saved=self.preferences.get('interface_id')
        if saved:self.interface.addItem(self.preferences.get('interface_label',saved),saved)
    def capture_setup_help(self):
        d=Editor(self,'抓包组件安装说明');d.save.hide()
        d.form.addRow(label('首次使用实时监听：安装Windows版Wireshark，并按官方安装流程安装Npcap。已有安装可直接复用，不需要再装完整开发环境。'))
        d.form.addRow(label('安装完成后回到设置，点击“重新检测 dumpcap”，选择实际联网网卡并保存。离线导入pcap/pcapng不需要Npcap；无需启动Wireshark界面。'))
        d.form.addRow(label('dumpcap是捕获程序，Npcap是系统驱动。随包dumpcap也不能替代驱动；本程序不会静默安装或替换驱动。','hint'))
        d.actions.insertWidget(1,self.action('Wireshark官方下载',lambda:QDesktopServices.openUrl(QUrl('https://www.wireshark.org/download.html'))))
        d.actions.insertWidget(1,self.action('Npcap官方网站',lambda:QDesktopServices.openUrl(QUrl('https://npcap.com/'))))
        d.exec()
    def detect_dumpcap(self):
        path=find_dumpcap()
        if not path:self.notify('未找到dumpcap，请查看抓包组件安装说明');return
        self.dumpcap.setText(path);self.refresh_interfaces();self.notify('已检测dumpcap，请选择网卡并保存设置')

    def set_topmost(self,value):self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,bool(value)); self.show()
    def clear_player_identity(self):
        self.archive.save_settings({'own_player_key':None,'own_nickname':''});self.own_nickname.clear();self.preferences.update(own_player_key=None,own_nickname='');self.refresh_all();self.notify('已清除本号身份与昵称；本场手动方向记录保留')
    def browse_dumpcap(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 dumpcap',self.dumpcap.text(),'程序 (*.exe);;全部文件 (*)')
        if path:self.dumpcap.setText(path); self.refresh_interfaces()
    def save_preferences(self):
        values={'dumpcap':self.dumpcap.text().strip(),'port':self.port.value(),'topmost':self.topmost.isChecked(),'capture_context':self.capture_scene.currentData(),'own_nickname':self.own_nickname.text().strip()}
        if values['own_nickname']!=self.preferences.get('own_nickname',''):values['own_player_key']=None
        if self.interface.currentData():values.update(interface_id=self.interface.currentData(),interface_label=self.interface.currentText())
        self.archive.save_settings(values); self.preferences.update(values); self.refresh_all();self.notify('设置已保存')
    def refresh_interfaces(self):
        path=self.dumpcap.text().strip()
        if not path:raise ValueError('请先选择 dumpcap.exe')
        self.refresh_interfaces_btn.setEnabled(False)
        def worker():
            try:
                result=subprocess.run([path,'-D'],capture_output=True,timeout=12,**HIDE_CONSOLE)
                if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
                self.events.put(('global','interfaces',result.stdout.decode(errors='replace').splitlines()))
            except Exception as exc:self.events.put(('global','interface_error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def import_capture(self):
        path,_=QFileDialog.getOpenFileName(self,'导入本地抓包','','抓包 (*.pcap *.pcapng);;全部文件 (*)')
        if path:self.start_job(path=path)
    def start_live(self):
        if not self.dumpcap.text().strip() or not self.interface.currentData():self.navigate(5); self.notify('请选择 dumpcap 路径和实际联网网卡'); return
        self.start_job(dumpcap=self.dumpcap.text().strip(),interface=self.interface.currentData())
    def start_job(self,**kwargs):
        if self.job and self.job.thread.is_alive():return
        self.save_preferences(); self.token+=1; token=self.token; self.browsing=False; self.current_id=None; self.live_id=None; self.live_time=None; self.unsaved_battle=None; self.storage_failed=False; self.render_battle()
        self.capture_diagnostics={}; self.capture_info.setText('正在等待本次采集的数据…'); self.capture_scene.setEnabled(False)
        self.job=CaptureJob(lambda k,d:self.events.put((token,k,d)),self.port.value(),self.mappings,self.archive,self.capture_scene.currentData())
        self.start_btn.setEnabled(False); self.import_btn.setEnabled(False); self.stop_btn.setEnabled(True); self.connection.setText('●  正在导入' if kwargs.get('path') else '●  正在监听'); self.navigate(0); self.job.start(**kwargs)
    def stop_capture(self):
        if self.job:self.job.stop(); self.connection.setText('●  正在停止')
    def poll(self):
        for _ in range(300):
            try:token,kind,data=self.events.get_nowait()
            except queue.Empty:break
            if token!='global' and token!=self.token:continue
            try:self.handle_event(kind,data)
            except Exception as exc:self.archive.logger.exception('UI event %s failed',kind); self.notify('处理失败：'+str(exc))
    def handle_event(self,kind,data):
        if kind=='interfaces':
            saved=self.preferences.get('interface_id'); self.interface.clear()
            for line in data:
                match=re.match(r'^\d+\.\s+(\S+)',line)
                if match:self.interface.addItem(line,match.group(1))
            index=self.interface.findData(saved); self.interface.setCurrentIndex(index); self.refresh_interfaces_btn.setEnabled(True); self.notify('已刷新网卡，请选择实际联网网卡' if index<0 else '已恢复上次网卡')
        elif kind=='interface_error':self.refresh_interfaces_btn.setEnabled(True); self.notify(data)
        elif kind=='battle':
            bid=data.get('archive_id')
            if bid and not self.archive.is_deleted(bid):
                timestamp=data.get('capture_time') or 0
                if self.live_time is None or timestamp>=self.live_time:
                    self.live_id=bid; self.live_time=timestamp
                    if not self.browsing:self.current_id=bid; self.unsaved_battle=None; self.render_battle()
                if self.browsing and self.current_id==bid:self.render_battle()
                elif self.browsing:self.refresh_battle_navigation()
                self._stats_dirty=True;self._history_search_dirty=True;self.refresh_history()
                if self.stack.currentIndex()==1:self.refresh_stats(False)
            elif not bid:
                self.unsaved_battle=data
                if not self.browsing:self.current_id=None; self.render_battle()
        elif kind=='inventory':self.inventory_rows=data; self.render_inventory()
        elif kind=='inventory_snapshot':self.bag_snapshot=data; self.inventory_rows=data.get('loadout_rows',self.inventory_rows); self.render_inventory()
        elif kind=='diagnostics':self.render_capture_diagnostics(data)
        elif kind=='observation':
            if data.get('kind')=='settlement':
                self.refresh_records(); self.notify('结算已关联' if data.get('association_status','linked')=='linked' else '收到结算，但未计入本人结果；原因见读取诊断')
        elif kind=='counts':self.notify(f"分组 {data.get('packets',0)} · 游戏下行 {data.get('game_packets',0)} · 消息 {data.get('messages',0)} · 对局 {data.get('battles',0)}")
        elif kind=='storage_error':self.storage_failed=True; self.notify(str(data))
        elif kind=='warning':self.notify(str(data))
        elif kind=='error':QMessageBox.warning(self,'读取失败',str(data))
        elif kind=='done':
            self.capture_scene.setEnabled(True)
            self.start_btn.setEnabled(True); self.import_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.connection.setText('●  未监听'); self.refresh_all()
            self.notify('自动保存发生错误，请导出当前数据并查看日志' if self.storage_failed else '读取失败，已保存的数据保留，请查看日志' if data.get('failed') else '读取已结束，数据已保存')
    def refresh_records(self):
        self._stats_dirty=True;self._history_search_dirty=True
        self.render_battle();self.refresh_history()
        if self.stack.currentIndex()==1:self.refresh_stats(False)
    def refresh_all(self):
        self._stats_dirty=True;self._history_search_dirty=True
        self.render_battle(); self.render_inventory(); self.refresh_history(); self.render_mappings()
        if self.stack.currentIndex()==1:self.refresh_stats(False)
    def write_json(self,data,filename):
        if data is None:self.notify('暂无可导出的数据'); return
        path,_=QFileDialog.getSaveFileName(self,'导出 JSON',filename,'JSON (*.json)')
        if path:Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); self.notify('已导出 '+Path(path).name)
    def export_battle(self):
        if self.current_id:self.write_json({'version':VERSION,'original':self.archive.get(self.current_id)['original'],'display':self.latest,'manual_annotations':self.archive.get(self.current_id)['annotations'],'opponent':self.archive.get(self.current_id)['opponent'],'context':self.archive.context(self.current_id)},'etheria_battle.json')
        elif self.latest:self.write_json({'version':VERSION,'original':self.unsaved_battle,'display':self.latest,'saved':False},'etheria_unsaved_battle.json')
        else:self.notify('请先选择一场对局')
    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'备份数据库','etheria_backup.sqlite3','SQLite (*.sqlite3)')
        if path:self.archive.backup(path); self.notify('数据库已备份')
    def open_directory(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.archive.directory)))
    def observations(self):
        d=Editor(self,'本地观测 · 最近 100 条'); d.save.hide(); t=QPlainTextEdit(json.dumps(self.archive.observations(limit=100),ensure_ascii=False,indent=2)); t.setReadOnly(True); t.setMinimumHeight(300); d.form.addRow(t)
        d.actions.insertWidget(1,self.action('导出结算资料',lambda:self.write_json(self.archive.validation_dataset(),'etheria_result_validation.json'))); d.exec()
    def closeEvent(self,event):
        try:self.save_preferences()
        except Exception:self.archive.logger.exception('close preferences')
        if self.job and self.job.thread.is_alive():
            self.job.stop(); self.notify('正在停止抓包，请稍候…'); self._closing=True; self.setEnabled(False); event.ignore(); QTimer.singleShot(100,self.finish_close); return
        self.timer.stop(); event.accept()
    def finish_close(self):
        if self.job and self.job.thread.is_alive():QTimer.singleShot(100,self.finish_close)
        else:self.setEnabled(True); self.close()

def main():
    app=QApplication(sys.argv); app.setApplicationName('EtheriaAssistant'); app.setOrganizationName('EtheriaAssistant')
    from runtime_lock import RuntimeLock
    from storage import data_directory
    try:
        with RuntimeLock(data_directory()):
            window=MainWindow(); window.show(); return app.exec()
    except RuntimeError as exc:
        QMessageBox.information(None,'伊瑟 · 对局助手',str(exc)); return 1

if __name__=='__main__':sys.exit(main())


