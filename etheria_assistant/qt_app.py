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
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QLineEdit, QSpinBox, QCheckBox, QPlainTextEdit, QTabWidget, QDialog,
    QDialogButtonBox, QFormLayout, QFileDialog, QMessageBox, QButtonGroup, QSplitter, QBoxLayout)
from capture import CaptureJob, find_dumpcap, shell_text, matrix_text, imprint_text, HIDE_CONSOLE
from core import load_mappings, shell_config_name, matrix_name
from storage import Archive, project_unit, unit_key, shell_candidates
from analytics import analyse, rank_statistics
from theme import STYLE
from equipment import (project_gear, attribute_text, matches_gear, normalize_filters,
                       filter_options, filter_summary, RARITIES, UNKNOWN, ATTRIBUTES,
                       normalize_sort, sort_gear, gear_sort_value)
from inventory_widgets import GearFilterDialog

VERSION='2.6.5'
CATEGORIES={'角色编号':'heroes','智壳配置编号':'shell_configs','智壳战斗效果编号':'shell_effects',
            '矩阵库存编号':'matrices','矩阵战斗效果编号':'matrix_effects'}
KINDS=['未分类','BP排位','竞技场','练习/测试']
RESULTS={'等待结算':'unknown','胜利':'A','失败':'B','平局':'draw'}

def label(text, name=None):
    w=QLabel(str(text)); w.setWordWrap(True)
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
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    w.horizontalHeader().setStretchLastSection(True); w.setWordWrap(False)
    w.verticalHeader().setDefaultSectionSize(42)
    return w

def fill(w, rows):
    w.setUpdatesEnabled(False); w.setRowCount(len(rows))
    for r,values in enumerate(rows):
        for c,value in enumerate(values):
            item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); w.setItem(r,c,item)
    w.setUpdatesEnabled(True)

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
        self.mappings=self.archive.mappings(load_mappings()); self.events=queue.Queue()
        self.job=None; self.token=0; self.current_id=None; self.live_id=None; self.browsing=False
        self.live_time=None; self.capture_diagnostics=self.preferences.get('last_capture_diagnostics',{})
        self.latest=None; self.unsaved_battle=None; self.storage_failed=False; self.inventory_rows=[]; self.history_offset=0; self.history_ids=[]
        saved=self.archive.latest_inventory(); self.bag_snapshot=saved['data'] if saved else None
        self.gear_filters=normalize_filters(self.preferences.get('gear_filters',{}))
        self.gear_sort=normalize_sort(self.preferences.get('gear_sort',{}))
        self.gear_metadata=self.archive.gear_metadata()
        if self.bag_snapshot:self.inventory_rows=self.bag_snapshot.get('loadout_rows',[])
        self.setWindowTitle('伊瑟 · 对局助手 '+VERSION); self.resize(1536,960); self.setMinimumSize(1050,700)
        self.setStyleSheet(STYLE); self.setup(); self.refresh_all()
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(80)
        self.set_topmost(self.preferences.get('topmost',False))
        self.archive.logger.info('Qt application %s started',VERSION)
        if not self.preferences.get('interface_id'):self.navigate(5)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'teams_layout'):
            direction=QBoxLayout.Direction.TopToBottom if self.width()<1400 else QBoxLayout.Direction.LeftToRight
            self.teams_layout.setDirection(direction); self.dash_layout.setDirection(direction)

    def guarded(self,action):
        try:return action()
        except Exception as exc:
            self.archive.logger.exception('UI action failed'); QMessageBox.warning(self,'操作失败',str(exc))
    def action(self,text,fn,primary=False):return button(text,lambda:self.guarded(fn),primary)
    def notify(self,text):self.statusBar().showMessage(str(text))
    def setup(self):
        central=QWidget(); self.setCentralWidget(central); outer=QHBoxLayout(central); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(185); s=QVBoxLayout(side); s.setContentsMargins(0,24,0,20)
        brand=QWidget(); br=QVBoxLayout(brand); br.setContentsMargins(18,0,8,0); br.addWidget(label('ETHERIA','eyebrow')); br.addWidget(label('伊瑟 · 对局助手','brand')); br.addWidget(label('LOCAL COMPANION','hint')); s.addWidget(brand); s.addSpacing(22)
        self.nav=QButtonGroup(self); self.stack=QStackedWidget()
        for i,text in enumerate(['◈   对局总览','▥   战绩统计','▦   源器与配装','◷   历史与日志','⌘   编号映射','⚙   连接与设置']):
            b=QPushButton(text); b.setCheckable(True); b.setObjectName('nav'); self.nav.addButton(b,i); s.addWidget(b)
        self.nav.idClicked.connect(self.navigate); s.addStretch()
        foot=QWidget(); ft=QVBoxLayout(foot); ft.setContentsMargins(18,0,8,0); ft.addWidget(label('数据仅保存在本机','hint')); ft.addWidget(label('DESKTOP  /  '+VERSION,'hint')); s.addWidget(foot); outer.addWidget(side)
        main=QWidget(); m=QVBoxLayout(main); m.setContentsMargins(18,18,18,12); m.setSpacing(14)
        top=QHBoxLayout(); self.page_title=label('对局总览','title'); top.addWidget(self.page_title); top.addStretch()
        self.connection=label('●  未监听','hint'); top.addWidget(self.connection)
        self.import_btn=self.action('导入抓包',self.import_capture); top.addWidget(self.import_btn)
        self.start_btn=self.action('开始监听',self.start_live,True); top.addWidget(self.start_btn)
        self.stop_btn=self.action('停止',self.stop_capture); self.stop_btn.setEnabled(False); top.addWidget(self.stop_btn); m.addLayout(top)
        m.addWidget(self.stack,1); outer.addWidget(main,1)
        self.build_battle(); self.build_stats(); self.build_inventory(); self.build_history(); self.build_mappings(); self.build_settings()
        self.navigate(0); self.notify('准备就绪 · 原有数据库和用户映射会自动沿用')
    def navigate(self,index):
        self.stack.setCurrentIndex(index); self.nav.button(index).setChecked(True)
        self.page_title.setText(['对局总览','战绩统计','源器与配装','历史与日志','编号映射','连接与设置'][index])
        if index==1:self.refresh_stats()
        if index==3:self.refresh_history()
    def page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0); layout.setSpacing(14); self.stack.addWidget(page); return layout
    def card(self):
        card=QFrame(); card.setObjectName('card'); layout=QVBoxLayout(card); layout.setContentsMargins(14,14,14,14); layout.setSpacing(12); return card,layout
    def build_battle(self):
        layout=self.page(); bar=QHBoxLayout(); self.battle_info=label('等待进入战斗 · 可导入历史抓包','hint'); bar.addWidget(self.battle_info,1)
        bar.addWidget(self.action('返回最新',self.return_live)); bar.addWidget(self.action('对局分类',self.edit_context)); bar.addWidget(self.action('导出本场',self.export_battle)); layout.addLayout(bar)
        nav=QHBoxLayout(); self.previous_battle=self.action('上一场 · 较早',lambda:self.step_battle(1)); nav.addWidget(self.previous_battle)
        self.next_battle=self.action('下一场 · 较新',lambda:self.step_battle(-1)); nav.addWidget(self.next_battle)
        self.battle_jump=QComboBox(); self.battle_jump.setMinimumContentsLength(18); self.battle_jump.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.battle_jump.currentIndexChanged.connect(self.jump_battle); nav.addWidget(self.battle_jump,1)
        self.battle_position=label('','hint'); nav.addWidget(self.battle_position)
        nav.addWidget(self.action('返回历史日志',self.back_to_history)); layout.addLayout(nav)
        self.record_info=label('','hint'); layout.addWidget(self.record_info)
        diagnostic=QHBoxLayout(); self.capture_info=label('尚未开始本次采集','hint'); diagnostic.addWidget(self.capture_info,1)
        diagnostic.addWidget(self.action('读取诊断',self.show_capture_diagnostics)); layout.addLayout(diagnostic)
        QShortcut(QKeySequence('Alt+Left'),self,activated=lambda:self.step_battle(1) if self.stack.currentIndex()==0 else None)
        QShortcut(QKeySequence('Alt+Right'),self,activated=lambda:self.step_battle(-1) if self.stack.currentIndex()==0 else None)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); layout.addWidget(scroll,1)
        content=QWidget(); body=QVBoxLayout(content); body.setContentsMargins(0,0,0,0); body.setSpacing(14); scroll.setWidget(content)
        teams=QBoxLayout(QBoxLayout.Direction.LeftToRight); self.teams_layout=teams; teams.setSpacing(14); self.team_layouts={}; self.team_titles={}
        for team in ['A','B']:
            card,c=self.card(); title=label('⚔  己方队伍' if team=='A' else '⚔  敌方队伍','ownTeam' if team=='A' else 'enemyTeam'); c.addWidget(title)
            self.team_titles[team]=title
            roster=QVBoxLayout(); roster.setSpacing(0); c.addLayout(roster); c.addStretch(); self.team_layouts[team]=roster; teams.addWidget(card,1)
        body.addLayout(teams)
        row=QBoxLayout(QBoxLayout.Direction.LeftToRight); self.dash_layout=row; self.dash_tables=[]
        for title,subtitle in [('低胜率对位','遇上这些角色时的队伍胜率'),('高胜率搭配','同队出场组合的队伍胜率')]:
            card,c=self.card(); c.addWidget(label(title,'hero')); c.addWidget(label(subtitle+' · 最少 5 场胜负样本','hint'))
            t=table(['角色 / 对象','胜率','样本']); t.setMinimumHeight(185); t.setMaximumHeight(230); c.addWidget(t); row.addWidget(card,1); self.dash_tables.append(t)
        body.addLayout(row); body.addWidget(label('点击角色名字维护精确编号；“配装”仅修改本场记录。矩阵显示已下发效果，不能据此推算完整总点数。','hint'))
        body.addStretch()
    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().hide(); item.widget().deleteLater()
    def render_battle(self):
        self.latest=None
        self.record_info.setText('')
        if self.current_id and not self.archive.is_deleted(self.current_id):
            record=self.archive.get(self.current_id); self.latest=copy.deepcopy(record['original']); self.latest['status']=record['status']
            self.latest['tracking']=record.get('tracking') or self.latest.get('tracking')
            for team,units in self.latest['teams'].items():
                for i,u in enumerate(units):
                    key=unit_key(team,i,u); units[i]=project_unit(u,self.mappings,record['annotations'].get(key)); units[i]['annotation_key']=key
            ctx=self.archive.context(self.current_id)
            replay=self.latest.get('capture_context')=='replay'
            result_label='结果未确认' if replay and ctx['winner']=='unknown' else next(k for k,v in RESULTS.items() if v==ctx['winner'])
            self.battle_info.setText(f"{'历史查看' if self.browsing else '最新对局'} · {stamp(self.latest.get('capture_time'))} · {ctx['sample_kind']} · {result_label} · {'回放/观战' if replay else '己方视角'}")
            self.record_info.setText(('回放记录 · 不计本人战绩 · ' if replay else '')+record['status'])
        elif self.unsaved_battle:
            self.latest=copy.deepcopy(self.unsaved_battle)
            self.battle_info.setText('自动保存失败 · 当前数据仍可导出，请检查磁盘和运行日志')
        else:self.current_id=None; self.battle_info.setText('等待进入战斗 · 可导入历史抓包')
        self.refresh_battle_navigation()
        for team,layout in self.team_layouts.items():
            replay=bool(self.latest and self.latest.get('capture_context')=='replay')
            self.team_titles[team].setText(('记录 A 方' if team=='A' else '记录 B 方') if replay else ('⚔  己方队伍' if team=='A' else '⚔  敌方队伍'))
            self.clear_layout(layout)
            units=self.latest['teams'].get(team,[]) if self.latest else []
            if not units:layout.addWidget(label('暂无角色数据\n开始监听后，进入战斗将自动更新。','hint'))
            for unit in units:
                card=QFrame(); card.setObjectName('heroRow'); c=QHBoxLayout(card); c.setContentsMargins(4,10,4,10); c.setSpacing(8)
                names=QWidget(); names.setFixedWidth(125); n=QVBoxLayout(names); n.setContentsMargins(0,0,0,0); n.setSpacing(6)
                name=button(unit['hero_name'],lambda u=unit:self.guarded(lambda:self.edit_hero(u))); name.setObjectName('link'); name.setToolTip('点击修改名称 · #'+str(unit['hero_id'])); n.addWidget(name)
                actions=QHBoxLayout(); actions.setSpacing(6)
                for title,fn in [('配装',self.edit_loadout),('详情',self.details)]:
                    edit=self.action(title,lambda u=unit,f=fn:f(u)); edit.setObjectName('smallAction'); actions.addWidget(edit)
                n.addLayout(actions); c.addWidget(names)
                attributes=QWidget(); attributes.setFixedWidth(276); grid=QGridLayout(attributes)
                grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
                fields=[('hp','生命'),('attack','攻击'),('defense','防御'),('speed','速度'),
                        ('crit','暴击率'),('crit_damage','暴击伤害'),('effect_hit','效果命中'),('effect_resist','效果抵抗')]
                for index,(key,title) in enumerate(fields):
                    percentage=index>=4
                    values=(unit.get('percent_attributes_tentative') or {}) if percentage else unit['stats']
                    value=values.get(key)
                    shown='—'
                    if isinstance(value,(int,float)):
                        shown=f'{value:g}%' if percentage else f'{value:.2f}' if key=='speed' else f'{value:g}'
                    cell=QWidget(); cell.setFixedWidth((68,58,58,68)[index%4])
                    column=QVBoxLayout(cell); column.setContentsMargins(0,0,0,0); column.setSpacing(2)
                    heading=label(title,'attributeTitle'); heading.setWordWrap(False); column.addWidget(heading)
                    metric=label(shown,'speed' if key=='speed' else 'statValue'); metric.setWordWrap(False)
                    metric.setAccessibleName(f"{team}方 {unit['hero_id']} {title}")
                    metric.setToolTip(title+'：'+shown+(' · 沿用已观测百分比规则；未下发显示 —' if percentage else ''))
                    column.addWidget(metric); grid.addWidget(cell,index//4,index%4)
                c.addWidget(attributes)
                equipment=QWidget(); eq=QVBoxLayout(equipment); eq.setContentsMargins(0,0,0,0); eq.setSpacing(6)
                eq.addWidget(label('智壳 / 矩阵效果','attributeTitle'))
                eq.addWidget(label(shell_text(unit),'shell')); eq.addWidget(label(matrix_text(unit),'hint'))
                eq.addWidget(label(imprint_text(unit),'hint')); c.addWidget(equipment,1); layout.addWidget(card)
    def refresh_battle_navigation(self):
        rows=self.archive.history_directory(); self.battle_navigation=[r['id'] for r in rows]
        self.battle_jump.blockSignals(True); self.battle_jump.clear(); self.battle_jump.setPlaceholderText('选择已保存对局')
        results={'A':'胜利','B':'失败','unknown':'结果未知'}
        for row in rows:
            text=f"{stamp(row['capture_time'])} · {results.get(row['winner'],'结果未知')} · {row['source']}"
            self.battle_jump.addItem(text,row['id'])
        index=self.battle_jump.findData(self.current_id); self.battle_jump.setCurrentIndex(index); self.battle_jump.blockSignals(False)
        self.previous_battle.setEnabled(index>=0 and index<len(rows)-1)
        self.next_battle.setEnabled(index>0)
        self.battle_position.setText(f'第 {len(rows)-index} / {len(rows)} 场' if index>=0 else f'共 {len(rows)} 场')

    def browse_battle(self, bid):
        if bid and not self.archive.is_deleted(bid):
            self.current_id=bid; self.browsing=True; self.render_battle(); self.navigate(0)

    def step_battle(self, direction):
        # Refresh to skip records removed since this view was opened.
        ids=[r['id'] for r in self.archive.history_directory()]
        if self.current_id not in ids:return
        index=ids.index(self.current_id)+direction
        if 0<=index<len(ids):self.browse_battle(ids[index])

    def jump_battle(self):
        bid=self.battle_jump.currentData()
        if bid and bid!=self.current_id:self.browse_battle(bid)

    def back_to_history(self):
        ids=[r['id'] for r in self.archive.history_directory()]
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
        d.actions.insertWidget(1,self.action('导出读取诊断',lambda:self.write_json(self.capture_diagnostics,'etheria_capture_diagnostics.json'))); d.exec()

    def render_capture_diagnostics(self, data):
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
        d=Editor(self,u['hero_name']+' · 原始数据'); d.save.hide(); text=QPlainTextEdit(json.dumps(u,ensure_ascii=False,indent=2)); text.setReadOnly(True); text.setMinimumHeight(240); d.form.addRow(text)
        candidates=shell_candidates(u,self.mappings)
        for effect in candidates:d.form.addRow(self.action(f'命名智壳效果 #{effect}',lambda e=effect:self.edit_mapping('shell_effects',str(e))))
        d.exec()
    def edit_context(self,bid=None):
        bid=bid or self.current_id
        if not bid: self.notify('请先选择一场已保存对局'); return
        ctx=self.archive.context(bid); d=Editor(self,'对局分类')
        d.form.addRow('自动结果',label(next(k for k,v in RESULTS.items() if v==ctx['winner'])))
        kind=combo(KINDS,ctx['sample_kind']); group=QLineEdit(ctx['dataset_group'])
        d.form.addRow('对局类型',kind); d.form.addRow('分组 / 赛季',group)
        def save():
            self.archive.set_classification(bid,kind.currentText(),group.text()); self.refresh_all()
        d.on_save=save; d.exec()
    def hero_name(self,identifier):return self.mappings['heroes'].get(str(identifier),f'角色 #{identifier}')
    def build_stats(self):
        layout=self.page(); layout.addWidget(label('本地观测样本 · 对位反映整队结果，不能视为单挑克制或全服胜率。','hint'))
        bar=QHBoxLayout(); self.stats_kind=combo(['BP排位','竞技场','全部已分类','未分类','练习/测试']); self.stats_group=QLineEdit(); self.stats_group.setPlaceholderText('分组 / 赛季（可留空）')
        self.stats_focus=combo(['全部角色']); self.stats_focus.setMinimumWidth(170); self.stats_perspective=combo(['仅己方','双方队伍']); self.stats_min=QSpinBox(); self.stats_min.setRange(1,100000); self.stats_min.setValue(5); self.stats_min.setPrefix('最少样本 ')
        for w in [self.stats_kind,self.stats_group,self.stats_focus,self.stats_perspective,self.stats_min]:bar.addWidget(w)
        bar.addWidget(self.action('刷新',self.refresh_stats)); layout.addLayout(bar)
        self.stats_summary=label('','hero'); layout.addWidget(self.stats_summary)
        tabs=QTabWidget(); self.stat_tables=[]
        for title,headers in [('角色概览',['角色','精确编号','出场','胜','负','平','未知','胜率样本','胜率']),('对位 · 低胜率优先',['角色','对方角色','胜','负','胜率样本','胜率']),('搭配 · 高胜率优先',['角色一','角色二','胜','负','胜率样本','胜率'])]:
            t=table(headers); tabs.addTab(t,title); self.stat_tables.append(t)
        layout.addWidget(tabs,1); row=QHBoxLayout(); row.addStretch(); row.addWidget(self.action('导出分析数据集',lambda:self.write_json(self.archive.dataset(),'etheria_analysis_dataset.json'))); layout.addLayout(row)
        for w in [self.stats_kind,self.stats_focus,self.stats_perspective]:w.currentIndexChanged.connect(lambda _:self.refresh_stats())
        self.stats_min.valueChanged.connect(lambda _:self.refresh_stats()); self.stats_group.returnPressed.connect(self.refresh_stats)
    def refresh_stats(self):
        ds=self.archive.dataset(); kinds=('BP排位','竞技场') if self.stats_kind.currentText()=='全部已分类' else (self.stats_kind.currentText(),)
        result=analyse(ds,self.mappings,kinds,self.stats_group.text().strip(),'own' if self.stats_perspective.currentIndex()==0 else 'both')
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
        # Overview panels always use all classified matches, both teams, fixed minimum 5.
        dashboard=analyse(ds,self.mappings,('BP排位','竞技场'),perspective='own')
        for category,t in zip(['matchups','cooccurrences'],self.dash_tables):
            rows=[]
            for r in rank_statistics(dashboard,category,min_decided=5)[:4]:
                ids=[r['hero_id'],r['opponent_id']] if category=='matchups' else r['hero_ids']
                rows.append([' / '.join(self.hero_name(i) for i in ids),percent(r['win_rate']),r['decided']])
            fill(t,rows or [['暂无足够的已分类样本','—','—']])
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
        self.component_table=table(['元件编号','配置编号（待对照）','属性项数','装配引用'])
        tabs.addTab(self.component_table,'元件 · 原始数据')
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
        references={}
        for group in snap.get('component_groups',[]):
            for slot,uid in enumerate(group.get('component_uids_raw',[]),1):
                if uid:references.setdefault(uid,[]).append(f"分组{group['id_raw']} · 槽{slot}")
        component_rows=[];self.component_display=[]
        for item in snap.get('components',[]):
            values=[item['uid'],item.get('config_id_raw','—'),len(item.get('attributes_raw',[])),
                    ' / '.join(references.get(item['uid'],[])) or '无已观测引用']
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
            self.gear_details.setPlainText('元件仅记录登录快照。选择元件查看原值；属性名称、字段3/6及装配分组类型尚待对照，源器分类和属性排序不作用于元件。');return
        self.gear_details.setPlainText(json.dumps(self.component_display[row],ensure_ascii=False,indent=2))
    def gear_detail(self):
        row=self.gear_table.currentRow()
        if 0<=row<len(self.gear_display):
            gear=self.gear_display[row]; p=project_gear(gear,self.gear_metadata.get(gear['uid']))
            text='\n'.join(('主属性：' if i==0 else '副属性：')+attribute_text(a)+
                           (f" · 追加次数 {a['upgrade_count_tentative']}（观测推定）" if i else '') for i,a in enumerate(p['attributes']))
            self.gear_details.setPlainText(text+'\n\n原始记录：\n'+json.dumps(gear,ensure_ascii=False,indent=2))
    def build_history(self):
        layout=self.page(); row=QHBoxLayout(); self.history_info=label('','hint'); row.addWidget(self.history_info,1)
        for text,fn in [('上一页',lambda:self.history_page(-1)),('下一页',lambda:self.history_page(1)),('打开',self.open_history),('删除选中',self.delete_history),('恢复最近删除',self.restore_history)]:row.addWidget(self.action(text,fn))
        layout.addLayout(row); self.history_table=table(['时间','来源','状态','对方队伍','类型','结果']); layout.addWidget(self.history_table,1)
        self.history_table.cellDoubleClicked.connect(lambda r,c:self.open_history()); QShortcut(QKeySequence('Delete'),self.history_table,activated=self.delete_history)
        row=QHBoxLayout()
        for text,fn in [('修改对局分类',self.context_selected),('导出分析数据集',lambda:self.write_json(self.archive.dataset(),'etheria_analysis_dataset.json')),('打开日志目录',self.open_directory),('备份数据库',self.backup),('查看结算观测',self.observations)]:row.addWidget(self.action(text,fn))
        layout.addLayout(row); layout.addWidget(label('Ctrl / Shift 多选，Ctrl+A 选择当前页；删除后不参与统计，可恢复最近一批。','hint'))
    def refresh_history(self):
        total,records=self.archive.history(100,self.history_offset)
        if not records and self.history_offset and total:self.history_offset=max(0,((total-1)//100)*100); total,records=self.archive.history(100,self.history_offset)
        self.history_ids=[r['id'] for r in records]; rows=[]
        for r in records:
            c=self.archive.context(r['id']); rows.append([stamp(r['capture_time']),r['source'],r['status'],'敌方',c['sample_kind'],next(k for k,v in RESULTS.items() if v==c['winner'])])
        fill(self.history_table,rows); self.history_info.setText(f'{total} 场记录 · 第 {self.history_offset//100+1} 页')
    def history_page(self,direction):
        total,_=self.archive.history(1); offset=max(0,self.history_offset+direction*100)
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
        removed=self.archive.trash_battles(ids)
        if self.current_id in removed:self.current_id=None; self.browsing=False
        if self.live_id in removed:self.live_id=None
        self.refresh_all(); self.notify(f'已删除 {len(removed)} 场，可恢复最近一批删除')
    def restore_history(self):
        restored=self.archive.restore_last_trash(); self.refresh_all(); self.notify(f'已恢复 {len(restored)} 场')
    def return_live(self):
        self.browsing=False; self.current_id=self.live_id if self.live_id and not self.archive.is_deleted(self.live_id) else None; self.render_battle()
    def build_mappings(self):
        layout=self.page(); row=QHBoxLayout(); self.map_category=combo(list(CATEGORIES)); self.map_query=QLineEdit(); self.map_query.setPlaceholderText('搜索编号或名称'); row.addWidget(self.map_category); row.addWidget(self.map_query,1)
        row.addWidget(self.action('新增 / 修改',self.edit_selected_mapping)); row.addWidget(self.action('恢复内置',self.restore_mapping)); row.addWidget(self.action('智壳候选编号清单',self.shell_catalogue)); layout.addLayout(row)
        self.mapping_table=table(['编号','名称','效果档位','来源']); layout.addWidget(self.mapping_table,1)
        self.mapping_table.cellDoubleClicked.connect(lambda r,c:self.edit_selected_mapping()); self.map_category.currentIndexChanged.connect(lambda _:self.render_mappings()); self.map_query.textChanged.connect(lambda _:self.render_mappings())
        layout.addWidget(label('用户映射优先于内置名称。角色皮肤按精确编号维护；本场配装修正不会改动原始数据。','hint'))
    def render_mappings(self):
        category=CATEGORIES[self.map_category.currentText()]; builtin=load_mappings()[category]; rows=[]; query=self.map_query.text().strip().lower()
        for identifier,value in sorted(self.mappings[category].items(),key=lambda x:int(x[0])):
            threshold=value.get('threshold') if isinstance(value,dict) else None
            shown_threshold=threshold if threshold is not None else '待确认' if category=='matrix_effects' else ''
            row=[identifier,value.get('name','') if isinstance(value,dict) else value,shown_threshold, '内置' if builtin.get(identifier)==value else '用户映射']
            if not query or query in ' '.join(map(str,row)).lower():rows.append(row)
        fill(self.mapping_table,rows)
    def edit_selected_mapping(self):
        row=self.mapping_table.currentRow(); identifier=self.mapping_table.item(row,0).text() if row>=0 else ''
        self.edit_mapping(CATEGORIES[self.map_category.currentText()],identifier)
    def edit_mapping(self,category,identifier=''):
        value=self.mappings[category].get(identifier,''); d=Editor(self,'编号名称映射')
        code=QLineEdit(identifier); name=QLineEdit(value.get('name','') if isinstance(value,dict) else value); points=QSpinBox(); points.setRange(0,999); points.setSpecialValueText('待确认'); points.setValue((value.get('threshold') or 0) if isinstance(value,dict) else 0)
        d.form.addRow('编号',code); d.form.addRow('名称',name)
        if category=='matrix_effects':d.form.addRow('生效档位',points)
        def save():self.archive.set_mapping(category,code.text(),name.text(),points.value() or None); self.mapping_changed()
        d.on_save=save; d.exec()
    def restore_mapping(self):
        row=self.mapping_table.currentRow()
        if row>=0:self.archive.remove_mapping(CATEGORIES[self.map_category.currentText()],self.mapping_table.item(row,0).text()); self.mapping_changed()
    def mapping_changed(self):self.mappings=self.archive.mappings(load_mappings()); self.refresh_all()
    def shell_catalogue(self):
        d=Editor(self,'智壳候选编号 · 双击命名'); d.resize(850,600); d.save.hide(); t=table(['效果编号','名称','状态','对局数','角色']); rows=self.archive.shell_catalogue(self.mappings)
        fill(t,[[r['id'],r['name'],r['status'],r['battle_count'],' / '.join(r['heroes'])] for r in rows]); t.setMinimumHeight(330); d.form.addRow(t)
        def edit(r,c):self.edit_mapping('shell_effects',str(rows[r]['id'])); d.accept()
        t.cellDoubleClicked.connect(edit); d.exec()
    def build_settings(self):
        layout=self.page(); card,c=self.card(); form=QFormLayout(); c.addLayout(form); layout.addWidget(card); layout.addStretch()
        self.dumpcap=QLineEdit(self.preferences.get('dumpcap') or find_dumpcap()); line=QHBoxLayout(); line.addWidget(self.dumpcap,1); line.addWidget(self.action('浏览',self.browse_dumpcap)); form.addRow('dumpcap 路径',line)
        self.interface=QComboBox(); self.interface.setMinimumWidth(440); line=QHBoxLayout(); line.addWidget(self.interface,1); self.refresh_interfaces_btn=self.action('刷新网卡',self.refresh_interfaces); line.addWidget(self.refresh_interfaces_btn); form.addRow('监听网卡',line)
        self.port=QSpinBox(); self.port.setRange(1,65535)
        try:self.port.setValue(int(self.preferences.get('port',20001)))
        except (ValueError,TypeError):self.port.setValue(20001)
        form.addRow('游戏端口',self.port); self.topmost=QCheckBox('窗口置顶'); self.topmost.setChecked(bool(self.preferences.get('topmost',False))); form.addRow(self.topmost); self.topmost.toggled.connect(self.set_topmost)
        self.capture_scene=QComboBox(); self.capture_scene.addItem('本人对局','live'); self.capture_scene.addItem('他人回放 / 观战（不计本人战绩）','replay')
        self.capture_scene.setCurrentIndex(max(0,self.capture_scene.findData(self.preferences.get('capture_context','live')))); form.addRow('采集场景',self.capture_scene)
        form.addRow(label('此项由你选择，不是协议自动识别。观看他人回放前选择回放场景，再开始监听。','hint'))
        c.addWidget(self.action('保存设置',self.save_preferences,True)); c.addWidget(label('使用已安装的 Wireshark / dumpcap 和 Npcap。网卡刷新在后台执行，抓包只在你点击开始后运行。','hint'))
        c.addWidget(label('此版本不附带驱动或第三方抓包程序；可继续使用原安装。额外素材与服务支出：0 元。','hint'))
        saved=self.preferences.get('interface_id')
        if saved:self.interface.addItem(self.preferences.get('interface_label',saved),saved)
    def set_topmost(self,value):self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,bool(value)); self.show()
    def browse_dumpcap(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 dumpcap',self.dumpcap.text(),'程序 (*.exe);;全部文件 (*)')
        if path:self.dumpcap.setText(path); self.refresh_interfaces()
    def save_preferences(self):
        values={'dumpcap':self.dumpcap.text().strip(),'port':self.port.value(),'topmost':self.topmost.isChecked(),'capture_context':self.capture_scene.currentData()}
        if self.interface.currentData():values.update(interface_id=self.interface.currentData(),interface_label=self.interface.currentText())
        self.archive.save_settings(values); self.preferences.update(values); self.notify('设置已保存')
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
                self.refresh_history(); self.refresh_stats()
            elif not bid:
                self.unsaved_battle=data
                if not self.browsing:self.current_id=None; self.render_battle()
        elif kind=='inventory':self.inventory_rows=data; self.render_inventory()
        elif kind=='inventory_snapshot':self.bag_snapshot=data; self.inventory_rows=data.get('loadout_rows',self.inventory_rows); self.render_inventory()
        elif kind=='diagnostics':self.render_capture_diagnostics(data)
        elif kind=='observation':
            if data.get('kind')=='settlement':
                self.render_battle(); self.refresh_history(); self.refresh_stats(); self.notify('结算已关联' if data.get('association_status','linked')=='linked' else '收到结算，但未计入本人结果；原因见读取诊断')
        elif kind=='counts':self.notify(f"分组 {data.get('packets',0)} · 游戏下行 {data.get('game_packets',0)} · 消息 {data.get('messages',0)} · 对局 {data.get('battles',0)}")
        elif kind=='storage_error':self.storage_failed=True; self.notify(str(data))
        elif kind=='warning':self.notify(str(data))
        elif kind=='error':QMessageBox.warning(self,'读取失败',str(data))
        elif kind=='done':
            self.capture_scene.setEnabled(True)
            self.start_btn.setEnabled(True); self.import_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.connection.setText('●  未监听'); self.refresh_all()
            self.notify('自动保存发生错误，请导出当前数据并查看日志' if self.storage_failed else '读取失败，已保存的数据保留，请查看日志' if data.get('failed') else '读取已结束，数据已保存')
    def refresh_all(self):self.render_battle(); self.render_inventory(); self.refresh_history(); self.render_mappings(); self.refresh_stats()
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
