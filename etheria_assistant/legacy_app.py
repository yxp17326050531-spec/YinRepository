"""2.2 desktop: observed battles, inventory and local analysis."""
from __future__ import annotations
import copy
import csv
import json
import os
import queue
import re
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from base_ui import App as BaseApp, CaptureJob, shell_text, matrix_text
from core import load_mappings, shell_config_name, matrix_name, shell_effect_mapping
from storage import Archive, project_unit, unit_key
from storage import shell_candidates
from ui_components import FormDialog
from features import CompanionFeatures

CATEGORIES = {'角色编号': 'heroes', '智壳配置编号': 'shell_configs', '智壳战斗效果编号': 'shell_effects',
              '矩阵库存编号': 'matrices', '矩阵战斗效果编号': 'matrix_effects'}


def parse_matrices(text):
    """One name and integer per line, split at the LAST comma."""
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.replace('，', ',').rsplit(',', 1)
        if len(parts) != 2:
            raise ValueError('每行填写“矩阵名称,点数”，例如：狂怒,9')
        result.append({'name': parts[0].strip(), 'points': int(parts[1].strip())})
    return result


class App(CompanionFeatures, BaseApp):
    def __init__(self, root, archive=None):
        self.archive = archive or Archive()
        self.preferences = self.archive.settings()
        self.current_id = None
        self.live_id = None
        self.live_data = None
        self.raw_current = None
        self.annotations = {}
        self.browsing = False
        self.history_offset = 0
        self.storage_failed = False
        self._booting = True
        super().__init__(root)
        self._booting = False
        saved_path = self.preferences.get('dumpcap', '')
        if saved_path and Path(saved_path).is_file():
            self.dumpcap.set(saved_path)
            if not self.interfaces:
                self.refresh_interfaces()
        self.port.set(str(self.preferences.get('port', 20001)))
        self.topmost.set(bool(self.preferences.get('topmost', True)))
        root.attributes('-topmost', self.topmost.get())
        self.opponent.bind('<<ComboboxSelected>>', self.set_opponent)
        ttk.Button(self.battle_toolbar, text='修改选中角色配装', command=self.edit_unit).pack(side='left')
        ttk.Button(self.battle_toolbar, text='返回最新对局', command=self.return_live).pack(side='left', padx=6)
        ttk.Button(self.battle_toolbar, text='补充智壳编号名称', command=self.name_shell).pack(side='left', padx=6)
        ttk.Button(self.battle_toolbar,text='角色编号改名',command=self.edit_hero_name).pack(side='left')
        self.tree.bind('<ButtonRelease-1>',self.name_cell_click,add='+')
        self.tree.bind('<Double-1>',self.battle_double_click)
        self.create_history_tab()
        self.create_mapping_tab()
        self.create_data_tabs()
        ttk.Button(self.battle_toolbar,text='标记胜负 / 类型',command=self.edit_context).pack(side='right')
        self.reload_history()
        if not self.preferences.get('interface_id'):
            self.notebook.select(self.connection_tab)
        root.title('伊瑟 · 对局助手 2.2.2')
        self.archive.logger.info('application 2.2.2 started')

    def refresh_interfaces(self):
        if self._booting:
            saved = self.preferences.get('dumpcap')
            if saved and Path(saved).is_file():
                self.dumpcap.set(saved)
        super().refresh_interfaces()

    def save_preferences(self):
        values = {'dumpcap': self.dumpcap.get().strip(), 'port': self.port.get(), 'topmost': self.topmost.get()}
        identity = self.interfaces.get(self.interface.get())
        if identity:
            values['interface_id'] = identity
        self.archive.save_settings(values)
        self.preferences.update(values)

    def start_job(self, **kwargs):
        if self.job and self.job.thread.is_alive():
            return
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror('端口无效', '端口应为 1–65535 的整数。')
            return
        try:
            self.save_preferences()
        except Exception as exc:
            messagebox.showerror('设置保存失败', str(exc))
            return
        self.current_id = self.live_id = None
        self.raw_current = self.live_data = None
        self.annotations = {}
        self.browsing = False
        self.storage_failed = False
        self.opponent.set('待选择')
        super().start_job(**kwargs)

    def load_record(self, bid, browsing):
        record = self.archive.get(bid)
        self.current_id = bid
        self.raw_current = record['original']
        self.annotations = record['annotations']
        self.raw_current['status'] = record['status']
        self.browsing = browsing
        self.opponent.set(record['opponent'])
        self.render_battle()

    def render_battle(self):
        if self.raw_current is None:
            self.latest = None
        else:
            self.latest = copy.deepcopy(self.raw_current)
            for team, units in self.latest['teams'].items():
                for i, unit in enumerate(units):
                    key = unit_key(team, i, unit)
                    units[i] = project_unit(unit, self.mappings, self.annotations.get(key))
                    units[i]['annotation_key'] = key
        super().render_battle()
        if self.latest:
            prefix = '历史查看 · ' if self.browsing else '最新对局 · '
            suffix = ' · 已自动保存' if self.current_id else ' · 未保存'
            self.battle_status.set(prefix + self.latest['status'] + suffix)

    def show_details(self, event=None):
        super().show_details(event)
        selected = self.tree.selection()
        if selected and selected[0] in self.unit_rows:
            unit = self.unit_rows[selected[0]]
            if unit.get('manual'):
                self.details.configure(state='normal')
                self.details.insert('end', '\n手动备注：' + (unit['manual'].get('note') or '无') + '；原始解析快照单独保留。')
                self.details.configure(state='disabled')

    def set_opponent(self, event=None):
        try:
            if self.current_id:
                self.archive.set_opponent(self.current_id, self.opponent.get())
                self.reload_history()
            self.render_battle()
            self.refresh_statistics()
        except Exception as exc:
            messagebox.showerror('保存失败', str(exc))

    def edit_unit(self):
        selected = self.tree.selection()
        if not selected or selected[0] not in self.unit_rows:
            messagebox.showinfo('先选择角色', '点击表格中的一名角色，再修改配装。')
            return
        if not self.current_id:
            messagebox.showerror('对局尚未保存', '本场自动保存未成功，暂不能持久化修改。请检查日志。')
            return
        unit = copy.deepcopy(self.unit_rows[selected[0]])
        bid, key = self.current_id, unit['annotation_key']
        annotation = self.annotations.get(key, {})
        window = FormDialog(self.root, '修改本场配装 · ' + unit['hero_name'])
        content = window.content
        ttk.Label(content, text='仅修改这场的这个角色。保存按钮固定在窗口顶部。', wraplength=510).pack(anchor='w', pady=(0, 12))
        shell_enabled = tk.BooleanVar(value=annotation.get('shell') is not None)
        ttk.Checkbutton(content, text='手动填写智壳', variable=shell_enabled).pack(anchor='w')
        shell = tk.StringVar(value=annotation.get('shell') or '')
        shell_entry = ttk.Combobox(content, textvariable=shell, values=sorted(set(self.mappings['shell_configs'].values())))
        shell_entry.pack(fill='x', pady=6)
        shell.trace_add('write', lambda *args: shell_enabled.set(True) if shell.get().strip() else None)
        matrix_enabled = tk.BooleanVar(value=annotation.get('matrices') is not None)
        ttk.Checkbutton(content, text='手动填写矩阵（勾选后留空表示手动记录为无）', variable=matrix_enabled).pack(anchor='w', pady=(8, 0))
        ttk.Label(content, text='每行：名称,点数   例如：狂怒,9', style='Hint.TLabel').pack(anchor='w')
        matrix = tk.Text(content, width=40, height=5, font=('Microsoft YaHei UI', 10))
        matrix.pack(fill='x', pady=6)
        matrix.insert('1.0', '\n'.join(f"{m['name']},{m['points']}" for m in annotation.get('matrices') or []))
        matrix.edit_modified(False)
        def matrix_changed(event):
            if matrix.edit_modified():
                matrix_enabled.set(True)
                matrix.edit_modified(False)
        matrix.bind('<<Modified>>', matrix_changed)
        ttk.Label(content, text='备注').pack(anchor='w')
        note = tk.Text(content, width=40, height=3, font=('Microsoft YaHei UI', 10))
        note.pack(fill='x', pady=6)
        note.insert('1.0', annotation.get('note', ''))
        actions = window.actions

        def commit(clear=False):
            try:
                if clear:
                    self.archive.clear_annotation(bid, key)
                else:
                    self.archive.annotate(bid, key, shell.get() if shell_enabled.get() else None,
                                          parse_matrices(matrix.get('1.0', 'end')) if matrix_enabled.get() else None,
                                          note.get('1.0', 'end').strip())
                if self.current_id == bid:
                    self.load_record(bid, self.browsing)
                self.status.set('本场手动配装已保存。' if not clear else '已清除本场手动配装。')
                window.destroy()
            except Exception as exc:
                messagebox.showerror('无法保存', str(exc), parent=window)

        ttk.Button(actions, text='保存修改', command=commit).pack(side='left')
        ttk.Button(actions, text='清除手动修改', command=lambda: commit(True)).pack(side='left', padx=8)
        ttk.Button(actions, text='取消', command=window.destroy).pack(side='right')
        window.bind('<Control-Return>', lambda event: commit())
        window.finish(shell_entry)

    def name_shell(self, effect_id=None, on_saved=None):
        if effect_id is None:
            selected = self.tree.selection()
            if not selected or selected[0] not in self.unit_rows:
                messagebox.showinfo('先选择角色', '点击一名角色，再补充智壳编号名称。')
                return
            unit = self.unit_rows[selected[0]]
            candidates = shell_candidates(unit, self.mappings)
            context = unit['hero_name']
        else:
            candidates = [effect_id]
            context = '历史编号清单'
        if not candidates:
            messagebox.showinfo('暂无候选编号', '这个角色没有当前规则能定位的智壳候选编号。请保留原始抓包供继续分析。')
            return
        window = FormDialog(self.root, '补充智壳编号名称')
        content = window.content
        ttk.Label(content, text=f'来源：{context}', wraplength=520).pack(anchor='w', pady=(0,10))
        ttk.Label(content, text='请根据自己这场的实际智壳确认名称。保存后，所有出现相同编号的角色都会更新名称。', wraplength=520).pack(anchor='w', pady=(0,12))
        ttk.Label(content, text='智壳相关效果编号（范围筛选结果为候选）').pack(anchor='w')
        identifier = tk.StringVar()
        picker = ttk.Combobox(content, textvariable=identifier, state='readonly', values=list(map(str,candidates)))
        picker.pack(fill='x', pady=8)
        ttk.Label(content, text='已确认的智壳名称').pack(anchor='w')
        name = tk.StringVar()
        names = set(self.mappings['shell_configs'].values()) | {m['name'] for m in self.mappings['shell_effects'].values()}
        entry = ttk.Combobox(content, textvariable=name, values=sorted(names))
        entry.pack(fill='x', pady=8)
        ttk.Label(content, text='多个候选时请逐个核对。仅凭编号或相邻数字，不能确认中文名称，也不自动合并技能变体。', wraplength=520, style='Hint.TLabel').pack(anchor='w', pady=10)

        def selected_id(*args):
            value = shell_effect_mapping(self.mappings, int(identifier.get())) or {}
            name.set(value.get('name',''))
        identifier.trace_add('write', selected_id)
        if len(candidates) == 1:
            identifier.set(str(candidates[0]))

        def save():
            try:
                if not identifier.get():
                    raise ValueError('请选择要命名的编号')
                self.archive.set_mapping('shell_effects', identifier.get(), name.get())
                self.mappings_changed()
                if on_saved:
                    on_saved()
                self.status.set(f'已保存用户映射：{identifier.get()} → {name.get().strip()}')
                window.destroy()
            except Exception as exc:
                messagebox.showerror('无法保存名称', str(exc), parent=window)
        ttk.Button(window.actions, text='保存编号名称', command=save).pack(side='left')
        ttk.Button(window.actions, text='取消', command=window.destroy).pack(side='right')
        window.bind('<Control-Return>', lambda event: save())
        window.finish(entry)

    def show_shell_catalogue(self):
        window = FormDialog(self.root, '已抓到的智壳候选编号 · 去重清单')
        info = tk.StringVar()
        ttk.Label(window.content, textvariable=info, wraplength=850).pack(anchor='w', pady=(0,8))
        tree = self.make_tree(window.content, [('id','效果编号',150), ('name','名称',150), ('state','识别状态',180),
                                               ('count','对局数',75), ('heroes','出现过的角色',360)], height=10)
        rows = []
        def refresh():
            rows[:] = self.archive.shell_catalogue(self.mappings)
            tree.delete(*tree.get_children())
            for row in rows:
                tree.insert('', 'end', iid=str(row['id']), values=(row['id'], row['name'] or '待确认', row['status'], row['battle_count'], '、'.join(row['heroes'])))
            info.set(f"历史共见到 {len(rows)} 个不同候选编号，{sum(not row['name'] for row in rows)} 个尚未命名。每个编号只需核对一次；范围筛选不代表全部已确认为智壳。")
        def edit():
            selected = tree.selection()
            if selected:
                self.name_shell(int(selected[0]), refresh)
        def export():
            path = filedialog.asksaveasfilename(parent=window, initialfile='etheria_shell_candidates.csv', defaultextension='.csv', filetypes=[('CSV','*.csv')])
            if not path:
                return
            try:
                with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['智壳候选效果编号','已对应名称','状态','出现对局数','角色观测次数','角色'])
                    for row in rows:
                        writer.writerow([row['id'],row['name'],row['status'],row['battle_count'],row['observations'],'、'.join(row['heroes'])])
                self.status.set('已导出去重后的智壳候选编号清单。')
            except Exception as exc:
                messagebox.showerror('导出失败', str(exc), parent=window)
        ttk.Button(window.actions, text='为选中编号补名称', command=edit).pack(side='left')
        ttk.Button(window.actions, text='导出清单 CSV', command=export).pack(side='left', padx=8)
        ttk.Button(window.actions, text='关闭', command=window.destroy).pack(side='right')
        tree.bind('<Double-1>', lambda event: edit())
        refresh()
        window.finish()

    def create_history_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text='历史与日志')
        actions = ttk.Frame(page)
        actions.pack(fill='x', pady=(0, 10))
        for title, command in [('刷新', self.reload_history), ('打开选中对局', self.open_history),
                               ('上一页', lambda: self.history_page(-1)), ('下一页', lambda: self.history_page(1)),
                               ('打开日志目录', self.open_directory), ('备份全部记录', self.backup)]:
            ttk.Button(actions, text=title, command=command).pack(side='left', padx=(0, 5))
        ttk.Button(actions,text='标记选中结果',command=lambda:self.edit_context(self.history_tree.selection()[0] if self.history_tree.selection() else None)).pack(side='left')
        self.history_info = tk.StringVar()
        ttk.Label(page, textvariable=self.history_info, style='Hint.TLabel').pack(anchor='w')
        self.history_tree = self.make_tree(page, [('time','对局时间（本机时区）',170), ('source','来源',180), ('status','状态',200), ('side','对方队伍',90),('kind','类型',90),('winner','胜方（手动）',100)], height=10)
        self.history_tree.configure(selectmode='extended')
        self.history_tree.bind('<Control-a>',self.select_history_page)
        self.history_tree.bind('<Delete>',lambda event:self.delete_history())
        self.history_tree.bind('<Double-1>', lambda event: self.open_history())
        deletion=ttk.Frame(page);deletion.pack(before=self.history_tree.master,fill='x',pady=(8,8))
        ttk.Button(deletion,text='删除选中（可恢复）',command=self.delete_history).pack(side='left')
        ttk.Button(deletion,text='恢复最近一批删除',command=self.restore_history).pack(side='left',padx=8)
        ttk.Label(deletion,text='Ctrl / Shift 多选，Ctrl+A 选择当前页；删除后不参与统计。',style='Hint.TLabel').pack(side='left')
        ttk.Label(page, text='对局自动保存；重复导入去重。运行日志按大小轮换，原始网络流量不自动保存。', style='Hint.TLabel').pack(anchor='w', pady=8)

    def reload_history(self):
        total, rows = self.archive.history(offset=self.history_offset)
        if not rows and self.history_offset:
            self.history_offset = max(0, ((total - 1) // 100) * 100)
            total, rows = self.archive.history(offset=self.history_offset)
        self.history_total = total
        self.history_tree.delete(*self.history_tree.get_children())
        for row in rows:
            stamp = datetime.fromtimestamp(row['capture_time']).strftime('%Y-%m-%d %H:%M:%S') if row['capture_time'] else row['saved_at']
            context = self.archive.context(row['id'])
            result = {'A':'A队胜','B':'B队胜','draw':'平局','unknown':'未知'}[context['winner']]
            self.history_tree.insert('', 'end', iid=row['id'], values=(stamp, row['source'], row['status'], row['opponent'],context['sample_kind'],result))
        self.history_info.set(f'共 {total} 场 · 第 {self.history_offset // 100 + 1} 页 · 每页最多 100 场')

    def history_page(self, delta):
        offset = self.history_offset + delta * 100
        if 0 <= offset < self.history_total:
            self.history_offset = offset
            self.reload_history()

    def open_history(self):
        selected = self.history_tree.selection()
        if selected:
            try:
                self.load_record(selected[0], True)
                self.notebook.select(self.battle_tab)
            except Exception as exc:
                messagebox.showerror('读取失败', str(exc))

    def return_live(self):
        if self.live_id:
            self.load_record(self.live_id, False)
        elif self.live_data:
            self.current_id = None
            self.raw_current, self.annotations, self.browsing = self.live_data, {}, False
            self.render_battle()
        else:
            messagebox.showinfo('暂无最新对局', '先监听或导入一场对局；已有记录在历史页。')

    def open_directory(self):
        if os.name == 'nt':
            os.startfile(str(self.archive.directory))
        else:
            messagebox.showinfo('日志目录', str(self.archive.directory))

    def backup(self):
        path = filedialog.asksaveasfilename(title='备份全部历史、手动修正和设置', initialfile='etheria_backup.sqlite3', defaultextension='.sqlite3')
        if path:
            try:
                self.archive.backup(path)
                self.status.set('完整数据库备份已保存。')
            except Exception as exc:
                messagebox.showerror('备份失败', str(exc))

    def create_mapping_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text='编号映射')
        ttk.Label(page, text='这里给编号命名，长期生效。修改某一场的配装，请到对局页双击角色。', style='Hint.TLabel').pack(anchor='w', pady=(0,8))
        ttk.Button(page, text='查看已抓到的智壳候选编号清单', command=self.show_shell_catalogue).pack(anchor='w', pady=(0,6))
        form = ttk.Frame(page)
        form.pack(fill='x', pady=8)
        self.map_category = ttk.Combobox(form, values=list(CATEGORIES), state='readonly', width=18)
        self.map_category.current(0)
        self.map_category.pack(side='left')
        self.map_id, self.map_name, self.map_threshold = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, variable, width in [('编号',self.map_id,14), ('名称',self.map_name,16), ('效果档位',self.map_threshold,5)]:
            ttk.Label(form, text=label).pack(side='left', padx=(10,4))
            ttk.Entry(form, textvariable=variable, width=width).pack(side='left')
        buttons = ttk.Frame(page)
        buttons.pack(fill='x', pady=(0,8))
        ttk.Button(buttons, text='保存名称映射', command=self.save_mapping).pack(side='left')
        ttk.Button(buttons, text='撤销该编号的用户映射', command=self.restore_mapping).pack(side='left', padx=8)
        ttk.Label(buttons, text='效果档位仅用于矩阵战斗效果；库存编号与战斗效果编号不同。', style='Hint.TLabel').pack(side='left')
        self.mapping_tree = self.make_tree(page, [('id','编号',180), ('name','名称',230), ('threshold','档位',90), ('source','来源',230)], height=10)
        self.mapping_tree.bind('<<TreeviewSelect>>', self.pick_mapping)
        self.map_category.bind('<<ComboboxSelected>>', self.change_mapping_category)
        self.reload_mapping_rows()

    def change_mapping_category(self, event=None):
        self.map_id.set(''); self.map_name.set(''); self.map_threshold.set('')
        self.reload_mapping_rows()

    def reload_mapping_rows(self):
        self.mapping_tree.delete(*self.mapping_tree.get_children())
        category = CATEGORIES[self.map_category.get()]
        builtin = load_mappings()[category]
        for identifier, value in sorted(self.mappings[category].items(), key=lambda item:int(item[0])):
            name = value.get('name') if isinstance(value, dict) else value
            threshold = value.get('threshold', '') if isinstance(value, dict) else ''
            source = '内置' if builtin.get(identifier) == value else '用户映射'
            self.mapping_tree.insert('', 'end', iid=identifier, values=(identifier, name, threshold, source))

    def pick_mapping(self, event=None):
        selected = self.mapping_tree.selection()
        if selected:
            values = self.mapping_tree.item(selected[0], 'values')
            self.map_id.set(values[0]); self.map_name.set(values[1]); self.map_threshold.set(values[2])

    def mappings_changed(self):
        self.mappings = self.archive.mappings(load_mappings())
        self.reload_mapping_rows()
        self.render_battle()
        self.render_inventory()
        self.render_gear()
        self.refresh_statistics()

    def save_mapping(self):
        try:
            self.archive.set_mapping(CATEGORIES[self.map_category.get()], self.map_id.get(), self.map_name.get(), self.map_threshold.get())
            self.mappings_changed()
            self.status.set('用户名称映射已保存，历史和当前显示已更新。')
        except Exception as exc:
            messagebox.showerror('映射保存失败', str(exc))

    def restore_mapping(self):
        try:
            self.archive.remove_mapping(CATEGORIES[self.map_category.get()], self.map_id.get())
            self.mappings_changed()
            self.status.set('已撤销用户映射，恢复内置名称或未知编号。')
        except Exception as exc:
            messagebox.showerror('无法恢复', str(exc))

    def render_inventory(self):
        for row in self.inventory_rows:
            row['hero_name'] = self.mappings['heroes'].get(str(row['hero_id']), f"角色 #{row['hero_id']}")
            config = row['shell_config_id']
            row['shell_name'] = shell_config_name(self.mappings, config)
            for m in row['matrices']:
                m['name'] = matrix_name(self.mappings, m['id'])
        super().render_inventory()

    def export(self):
        if not self.latest:
            messagebox.showinfo('暂无数据', '先选择一场对局。')
            return
        path = filedialog.asksaveasfilename(initialfile='etheria_battle_v2.json', defaultextension='.json', filetypes=[('JSON','*.json')])
        if path:
            try:
                output = {'version':'2.2.2', 'original':self.archive.get(self.current_id)['original'] if self.current_id else self.raw_current,
                          'display':self.latest, 'manual_annotations':self.annotations, 'opponent':self.opponent.get(),
                          'context':self.archive.context(self.current_id) if self.current_id else None}
                Path(path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
                self.status.set('已导出原始数据、当前显示和手动修正。')
            except Exception as exc:
                messagebox.showerror('导出失败', str(exc))

    def poll(self):
        for _ in range(300):
            try:
                token, kind, data = self.queue.get_nowait()
            except queue.Empty:
                break
            if token != 'global' and token != self.token:
                continue
            try:
                self.handle_event(kind, data)
            except Exception as exc:
                self.archive.logger.exception('UI event %s failed', kind)
                self.status.set('处理失败：' + str(exc) + '；请查看运行日志。')
        self.root.after(100, self.poll)

    def handle_event(self, kind, data):
        if kind == 'interfaces':
            self.interfaces = {line: re.match(r'^\d+\.\s+(\S+)', line).group(1) for line in data if re.match(r'^\d+\.\s+(\S+)', line)}
            current = self.preferences.get('interface_id')
            self.interface['values'] = list(self.interfaces)
            match = next((label for label, identity in self.interfaces.items() if identity == current), None)
            if match:
                self.interface.set(match)
            elif self.interface.get() not in self.interfaces:
                self.interface.set('')
            self.status.set('已恢复上次网卡。' if match else '请选择实际联网的网卡；启动后会自动记住。')
        elif kind in ('interface_error','storage_error','warning'):
            if kind == 'storage_error':
                self.storage_failed = True
            self.status.set(str(data))
        elif kind == 'battle':
            if data.get('archive_id') and self.archive.is_deleted(data['archive_id']):
                return
            self.live_data = data
            self.live_id = data.get('archive_id')
            self.reload_history()
            if not self.browsing:
                if self.live_id:
                    self.load_record(self.live_id, False)
                else:
                    self.current_id, self.raw_current, self.annotations = None, data, {}
                    self.render_battle()
        elif kind == 'inventory':
            self.inventory_rows = data
            self.inventory_status.set(f'收到 {len(data)} 条本号配装记录')
            self.render_inventory()
        elif kind == 'inventory_snapshot':
            self.bag_snapshot = data
            self.render_gear()
        elif kind == 'observation':
            if data.get('kind')=='settlement':
                self.observation_status.set('已保存结算观测；标记真实胜负后可导出验证资料。')
        elif kind == 'counts':
            self.counts.set(f"分组 {data.get('packets',0)} · 游戏下行 {data.get('game_packets',0)} · 消息 {data.get('messages',0)} · 对局 {data.get('battles',0)} · 提示 {data.get('warnings',0)}")
        elif kind == 'error':
            self.status.set('读取失败，请查看错误提示。')
            messagebox.showerror('读取失败', str(data))
        elif kind == 'done':
            self.start_button.configure(state='normal')
            self.import_button.configure(state='normal')
            self.stop_button.configure(state='disabled')
            self.reload_history()
            if data['failed']:
                self.status.set('读取失败，已解析的对局保留；详见运行日志。')
            elif self.storage_failed:
                self.status.set('读取已结束，但部分对局自动保存失败；请立即导出当前对局并查看运行日志。')
            else:
                self.status.set(f"{'已停止' if data['stopped'] else '读取完成'}：本次识别 {data['counts'].get('battles',0)} 场；历史对局已自动保存。")

    def close(self):
        try:
            self.save_preferences()
        except Exception:
            self.archive.logger.exception('save preferences failed at close')
        super().close()


if __name__ == '__main__':
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    try:
        App(root)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('启动失败', str(exc))
        raise
