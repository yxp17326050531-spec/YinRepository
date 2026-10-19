"""Windows desktop companion. Run with Python 3.10+ (Tkinter included)."""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import Engine, load_mappings

ROOT = Path(__file__).resolve().parent
HIDE_CONSOLE = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def find_dumpcap():
    executable_root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else ROOT
    candidates = [str(executable_root/'vendor'/'dumpcap'/'dumpcap.exe'),
                  str(ROOT/'vendor'/'dumpcap'/'dumpcap.exe'),shutil.which('dumpcap'),
                  str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Wireshark/dumpcap.exe'),
                  str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Wireshark/dumpcap.exe')]
    return next((p for p in candidates if p and Path(p).is_file()), '')


def number(value):
    return f'{value:g}' if isinstance(value, (int, float)) else '—'


def shell_text(unit):
    if unit.get('manual') and unit['manual'].get('shell'):
        return unit['manual']['shell'] + ' [手动]'
    if unit['shells']:
        return ' / '.join(s['name'] + (' [用户映射]' if s.get('confidence') == '用户映射' else ' [推定]' if '推定' in s.get('confidence','') else '') for s in unit['shells'])
    return '待识别' if unit['unknown_shell_effects'] else '未识别 / 未下发'


def matrix_text(unit):
    if unit.get('manual') and unit['manual'].get('matrices') is not None:
        items = unit['manual']['matrices']
        return ('、'.join(f"{m['name']} +{m['points']}" for m in items) or '无（手动填写）') + ' [手动]'
    found = unit['matrix_effects_candidates']
    labels = []
    for matrix in found:
        confidence = matrix.get('confidence', '')
        status = ('用户映射' if confidence == '用户映射' else
                  '已对照' if confidence == '已对照样本' else '候选')
        label = f"{matrix['name']} {matrix['threshold']}点效果（{status}）"
        if label not in labels:
            labels.append(label)
    return '、'.join(labels) if labels else '完整矩阵未知'


class CaptureJob:
    def __init__(self, emit, port, mappings, archive=None):
        self.emit = emit
        self.archive = archive
        self.source = ''
        self.engine = Engine(self.on_event, port, mappings)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.process = None
        self.thread = None

    def on_event(self, kind, data):
        if self.archive:
            if kind == 'battle':
                try:
                    bid = self.archive.save_battle(data, self.source)
                    data = dict(data, archive_id=bid)
                except Exception as exc:
                    self.emit('storage_error', '自动保存失败：' + str(exc))
                    self.archive.logger.exception('save_battle failed')
            elif kind in ('inventory_snapshot','observation'):
                try:
                    identity = (self.archive.save_inventory(data,self.source) if kind == 'inventory_snapshot'
                                else self.archive.save_observation(data,self.source))
                    data = dict(data,archive_id=identity)
                except Exception as exc:
                    self.emit('storage_error','资料保存失败：' + str(exc))
                    self.archive.logger.exception('save %s failed',kind)
            elif kind == 'warning':
                self.archive.logger.warning('%s', data)
        self.emit(kind, data)

    def start(self, path=None, dumpcap=None, interface=None):
        self.thread = threading.Thread(target=self.run, args=(path, dumpcap, interface), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def run(self, path, dumpcap, interface):
        self.source = ('导入：' + Path(path).name) if path else '实时监听'
        if self.archive:
            self.archive.logger.info('start %s', self.source)
        errors = []
        reader = None
        failed = False
        try:
            if path:
                with open(path, 'rb') as stream:
                    self.engine.read(stream, self.stop_event)
            else:
                command = [dumpcap, '-i', interface, '-f', f'tcp port {self.engine.port}', '-s', '0', '-q', '-w', '-']
                with self.lock:
                    if self.stop_event.is_set():
                        return
                    self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **HIDE_CONSOLE)

                def drain_stderr():
                    for line in iter(self.process.stderr.readline, b''):
                        errors.append(line.decode(errors='replace').strip())
                        del errors[:-12]

                reader = threading.Thread(target=drain_stderr, daemon=True)
                reader.start()
                self.engine.read(self.process.stdout, self.stop_event)
                code = self.process.wait(timeout=5)
                reader.join(timeout=1)
                if code and not self.stop_event.is_set():
                    raise RuntimeError('\n'.join(errors) or f'dumpcap 退出码 {code}')
        except Exception as exc:
            if not self.stop_event.is_set():
                failed = True
                detail = str(exc)
                if self.process and self.process.poll() is not None:
                    if reader:
                        reader.join(timeout=1)
                    if errors:
                        detail += '\n' + '\n'.join(errors)
                self.emit('error', detail)
                if self.archive:
                    self.archive.logger.error('%s', detail)
        finally:
            with self.lock:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
                if self.process:
                    self.process.stdout.close()
                    if reader:
                        reader.join(timeout=1)
                    self.process.stderr.close()
            self.emit('done', {'stopped': self.stop_event.is_set(), 'offline': bool(path),
                               'failed': failed, 'counts': dict(self.engine.counts)})
            if self.archive:
                self.archive.logger.info('done failed=%s counts=%s', failed, dict(self.engine.counts))


class App:
    def __init__(self, root):
        self.root = root
        root.title('伊瑟 · 对局助手 2.0')
        root.geometry('1320x840')
        root.minsize(1040, 650)
        root.configure(bg='#f3f5fa')
        self.queue = queue.Queue()
        self.job, self.token, self.latest = None, 0, None
        self.unit_rows = {}
        self.inventory_rows = []
        self.interfaces = {}
        self.mappings = self.archive.mappings(load_mappings()) if hasattr(self, 'archive') else load_mappings()
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10), background='#f3f5fa')
        style.configure('TButton', padding=(13, 8), borderwidth=0)
        style.configure('Accent.TButton', background='#315bd6',foreground='#ffffff',font=('Microsoft YaHei UI',10,'bold'))
        style.map('Accent.TButton',background=[('disabled','#c5ccdd'),('active','#244ab8')],foreground=[('disabled','#eef1f8')])
        style.configure('TNotebook',borderwidth=0,tabmargins=(0,5,0,0))
        style.configure('TNotebook.Tab',padding=(17,10),background='#e5eaf4',foreground='#56637b')
        style.map('TNotebook.Tab',background=[('selected','#ffffff')],foreground=[('selected','#284ebd')])
        style.configure('Card.TFrame',background='#ffffff')
        style.configure('TLabel', foreground='#26354c')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 21, 'bold'))
        style.configure('Hint.TLabel', foreground='#5c6d83')
        style.configure('Treeview', rowheight=42, background='#ffffff', fieldbackground='#ffffff', foreground='#26354c',borderwidth=0)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'), padding=10,background='#eef2fa',foreground='#425372',relief='flat')
        style.map('Treeview', background=[('selected', '#d9e8ff')], foreground=[('selected', '#132c50')])

        main = ttk.Frame(root, padding=18)
        main.pack(fill='both', expand=True)
        header = ttk.Frame(main)
        header.pack(fill='x')
        ttk.Label(header, text='伊瑟 · 对局助手', style='Title.TLabel').pack(side='left')
        self.topmost = tk.BooleanVar(value=True)
        ttk.Checkbutton(header, text='窗口置顶', variable=self.topmost,
                        command=lambda: root.attributes('-topmost', self.topmost.get())).pack(side='right')
        root.attributes('-topmost', True)
        ttk.Label(main, text='对局观察  ·  本地战绩  ·  源器资料', style='Hint.TLabel').pack(anchor='w', pady=(3, 14))

        notebook = ttk.Notebook(main)
        self.notebook = notebook
        self.connection_tab = ttk.Frame(notebook,padding=20)
        ttk.Label(self.connection_tab,text='首次使用时选择抓包程序和网络接口，之后会自动记住。',style='Hint.TLabel').pack(anchor='w',pady=(0,18))
        controls = ttk.Frame(self.connection_tab)
        controls.pack(fill='x', pady=(0, 8))
        self.dumpcap = tk.StringVar(value=find_dumpcap())
        ttk.Label(controls, text='抓包程序').grid(row=0, column=0, sticky='w')
        ttk.Entry(controls, textvariable=self.dumpcap).grid(row=0, column=1, columnspan=2, sticky='ew', padx=8)
        ttk.Button(controls, text='选择 dumpcap.exe', command=self.choose_dumpcap).grid(row=0, column=3)
        ttk.Label(controls, text='网络接口').grid(row=1, column=0, sticky='w', pady=8)
        self.interface = ttk.Combobox(controls, state='readonly')
        self.interface.grid(row=1, column=1, sticky='ew', padx=8)
        ttk.Button(controls, text='刷新接口', command=self.refresh_interfaces).grid(row=1, column=2)
        portbox = ttk.Frame(controls)
        portbox.grid(row=1, column=3)
        ttk.Label(portbox, text='游戏端口').pack(side='left', padx=6)
        self.port = tk.StringVar(value='20001')
        ttk.Entry(portbox, textvariable=self.port, width=7).pack(side='left')
        controls.columnconfigure(1, weight=1)

        actions = ttk.Frame(main)
        actions.pack(fill='x', pady=(0, 12))
        self.start_button = ttk.Button(actions, text='开始监听', command=self.start_live,style='Accent.TButton')
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=6)
        self.import_button = ttk.Button(actions, text='导入抓包', command=self.import_capture)
        self.import_button.pack(side='left')
        ttk.Button(actions, text='导出本场 JSON', command=self.export).pack(side='left', padx=6)
        ttk.Label(actions, text='对方队伍').pack(side='left', padx=(20, 6))
        self.opponent = ttk.Combobox(actions, state='readonly', values=('待选择', 'A 队', 'B 队'), width=8)
        self.opponent.set('待选择')
        self.opponent.pack(side='left')
        self.opponent.bind('<<ComboboxSelected>>', lambda event: self.render_battle())
        self.status = tk.StringVar(value='先选网络接口，再点开始监听；也可以导入已有抓包。')
        ttk.Label(main, textvariable=self.status, wraplength=1050).pack(anchor='w', pady=(0, 5))
        self.counts = tk.StringVar(value='尚未开始')
        ttk.Label(main, textvariable=self.counts, style='Hint.TLabel').pack(anchor='w', pady=(0, 9))

        notebook.pack(fill='both', expand=True)
        battle = ttk.Frame(notebook, padding=10)
        self.battle_tab = battle
        local = ttk.Frame(notebook, padding=10)
        notebook.add(battle, text='对局')
        notebook.add(local, text='本号配装')
        notebook.add(self.connection_tab,text='连接设置')
        self.battle_status = tk.StringVar(value='等待进入战斗')
        ttk.Label(battle, textvariable=self.battle_status).pack(anchor='w', pady=(0, 7))
        self.battle_toolbar = ttk.Frame(battle)
        self.battle_toolbar.pack(fill='x', pady=(0,6))
        self.tree = self.make_tree(battle, [('team','队伍',68), ('hero','角色',100), ('hp','生命',80), ('attack','攻击',66),
                                           ('defense','防御',66), ('speed','速度',62), ('shell','智壳',190), ('matrix','矩阵效果',300)], height=8)
        self.tree.bind('<<TreeviewSelect>>', self.show_details)
        self.details = tk.Text(battle, height=5, wrap='word', font=('Microsoft YaHei UI', 10), bg='#f7f9fc', fg='#41546d', relief='flat', padx=12, pady=8)
        self.details.pack(fill='x', pady=(8, 0))
        self.set_details('点击角色查看详情，双击可补充本场配装。\n已对照与候选效果分别标记；未显示效果不表示没有装备该矩阵。')
        self.tree.tag_configure('teamA',background='#f0f5ff')
        self.tree.tag_configure('teamB',background='#faf3fc')

        ttk.Label(local, text='登录时下发的本账号库存。这里只展示自己的配装，不能代替对手数据。', style='Hint.TLabel').pack(anchor='w', pady=(0, 8))
        filters = ttk.Frame(local)
        filters.pack(fill='x', pady=(0, 8))
        ttk.Label(filters, text='筛选角色').pack(side='left')
        self.query = tk.StringVar()
        ttk.Entry(filters, textvariable=self.query).pack(side='left', padx=8)
        self.query.trace_add('write', lambda *args: self.render_inventory())
        self.inventory_status = tk.StringVar(value='需要从登录前开始监听，或导入登录抓包。')
        ttk.Label(filters, textvariable=self.inventory_status, style='Hint.TLabel').pack(side='left')
        self.inv_tree = self.make_tree(local, [('hero','角色',130), ('mode','配装槽',110), ('shell','智壳',150), ('matrix','矩阵贡献（按编号统计）',530)], height=11)
        ttk.Label(local, text='未知编号单独保留，不自动合并；竞技槽含义尚待更多模式验证。', style='Hint.TLabel').pack(anchor='w', pady=8)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        if self.dumpcap.get():
            self.refresh_interfaces()

    def make_tree(self, parent, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', height=height, selectmode='browse')
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=width // 2, anchor='w' if key in ('hero','shell','matrix') else 'center')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky='nsew')
        scroll.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        return tree

    def choose_dumpcap(self):
        path = filedialog.askopenfilename(title='选择 Wireshark 文件夹里的 dumpcap.exe', filetypes=[('dumpcap', 'dumpcap.exe'), ('所有文件', '*')])
        if path:
            self.dumpcap.set(path)
            self.refresh_interfaces()

    def refresh_interfaces(self):
        executable = self.dumpcap.get().strip()
        if not executable or not Path(executable).is_file():
            self.status.set('未找到 dumpcap.exe，请选择 Wireshark 安装目录里的这个程序。')
            return
        self.status.set('正在读取网络接口…')

        def work():
            try:
                result = subprocess.run([executable, '-D'], capture_output=True, timeout=10, **HIDE_CONSOLE)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode(errors='replace'))
                lines = result.stdout.decode('utf-8', errors='replace').splitlines()
                self.queue.put(('global', 'interfaces', lines))
            except Exception as exc:
                self.queue.put(('global', 'interface_error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def start_job(self, **kwargs):
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror('端口无效', '端口应为 1–65535 的整数。')
            return
        if self.job and self.job.thread.is_alive():
            return
        self.token += 1
        token = self.token
        self.latest = None
        self.inventory_rows = []
        self.render_battle()
        self.render_inventory()
        self.inventory_status.set('等待本账号库存数据')
        self.counts.set('正在读取…')
        self.job = CaptureJob(lambda kind, data: self.queue.put((token, kind, data)), port, self.mappings, getattr(self, 'archive', None))
        self.start_button.configure(state='disabled')
        self.import_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('正在回放抓包…' if kwargs.get('path') else '监听已启动，等待游戏数据；请进入一场战斗。')
        self.job.start(**kwargs)

    def start_live(self):
        executable = self.dumpcap.get().strip()
        choice = self.interface.get()
        if not Path(executable).is_file() or choice not in self.interfaces:
            messagebox.showinfo('还差一步', '请选择 dumpcap.exe，刷新接口，并选中当前上网的网卡。')
            return
        self.start_job(dumpcap=executable, interface=self.interfaces[choice])

    def import_capture(self):
        path = filedialog.askopenfilename(title='导入抓包文件', filetypes=[('抓包文件', '*.pcapng *.pcap'), ('所有文件', '*')])
        if path:
            self.start_job(path=path)

    def stop(self):
        if self.job:
            self.job.stop()
            self.status.set('正在停止…')
            self.stop_button.configure(state='disabled')

    def render_battle(self):
        self.tree.delete(*self.tree.get_children())
        self.unit_rows.clear()
        if not self.latest:
            self.battle_status.set('等待进入战斗')
            self.set_details('等待对局数据。')
            return
        self.battle_status.set(self.latest['status'])
        selected = self.opponent.get()[:1]
        for team, units in self.latest['teams'].items():
            label = f'{team} 队' if selected not in ('A', 'B') else ('对方' if team == selected else '己方')
            for unit in units:
                stats = unit['stats']
                row = self.tree.insert('', 'end', tags=('team'+team,), values=(label, unit['hero_name'], *(number(stats[k]) for k in ('hp','attack','defense')), f"{stats['speed']:.2f}", shell_text(unit), matrix_text(unit)))
                self.unit_rows[row] = unit
        self.set_details('点击角色查看详情。双方默认用 A/B 标记，请按已知阵容选择对方队伍。\n完整矩阵配装未知；候选效果不等于总点数。')

    def set_details(self, text):
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', text)
        self.details.configure(state='disabled')

    def show_details(self, event=None):
        selected = self.tree.selection()
        if not selected or selected[0] not in self.unit_rows:
            return
        unit = self.unit_rows[selected[0]]
        pct = unit['percent_attributes_tentative']
        labels = [('crit','暴击'), ('crit_damage','暴伤'), ('effect_hit','效果命中'), ('effect_resist','效果抵抗')]
        line = '  '.join(f'{name} {number(pct.get(key))}%' for key, name in labels)
        self.set_details(f"{unit['hero_name']}  ·  编号 {unit['hero_id']}  ·  智壳：{shell_text(unit)}\n"
                         f"百分比属性（推定字段）：{line}\n"
                         f"矩阵：{matrix_text(unit)}；不能判断未出现的矩阵或精确总点数。\n"
                         f"效果编号：{', '.join(map(str, unit['effects_raw']))}")

    def render_inventory(self):
        self.inv_tree.delete(*self.inv_tree.get_children())
        query = self.query.get().strip()
        for row in self.inventory_rows:
            if query and query not in row['hero_name'] and query not in str(row['hero_id']):
                continue
            matrices = ' / '.join(f"{m['name']} +{m['points']}" for m in row['matrices']) or '待接收'
            if row['incomplete']:
                matrices += '（数据不全）'
            self.inv_tree.insert('', 'end', values=(row['hero_name'], row['mode'], row['shell_name'], matrices))

    def export(self):
        if not self.latest:
            messagebox.showinfo('暂无数据', '先读取一场战斗，再导出。')
            return
        path = filedialog.asksaveasfilename(title='导出本场已解析数据', initialfile='etheria_battle.json', defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                output = dict(self.latest, opponent_team_selected=self.opponent.get())
                Path(path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
                self.status.set(f'已导出：{Path(path).name}')
            except OSError as exc:
                messagebox.showerror('导出失败', str(exc))

    def poll(self):
        for _ in range(300):
            try:
                token, kind, data = self.queue.get_nowait()
            except queue.Empty:
                break
            if token != 'global' and token != self.token:
                continue
            if kind == 'interfaces':
                self.interfaces = {line: re.match(r'^(\d+)\.', line).group(1) for line in data if re.match(r'^(\d+)\.', line)}
                self.interface['values'] = list(self.interfaces)
                if self.interface.get() not in self.interfaces and self.interfaces:
                    self.interface.current(0)
                self.status.set('接口已列出。请选择实际联网的 Wi-Fi 或以太网网卡。' if self.interfaces else '未找到接口，请检查 Npcap 安装。')
            elif kind == 'interface_error':
                self.status.set('读取接口失败：' + data)
            elif kind == 'battle':
                self.latest = data
                self.render_battle()
            elif kind == 'inventory':
                self.inventory_rows = data
                self.inventory_status.set(f'收到 {len(data)} 条本号配装记录')
                self.render_inventory()
            elif kind == 'counts':
                self.counts.set(f"分组 {data.get('packets',0)}  ·  游戏下行 {data.get('game_packets',0)}  ·  消息 {data.get('messages',0)}  ·  对局 {data.get('battles',0)}  ·  提示 {data.get('warnings',0)}")
            elif kind == 'warning':
                self.status.set(data)
            elif kind == 'error':
                self.status.set('读取失败，请查看错误提示。')
                messagebox.showerror('读取失败', data + '\n\n若提示权限不足，请以管理员身份启动；若没有接口，请检查 Npcap。')
            elif kind == 'done':
                self.start_button.configure(state='normal')
                self.import_button.configure(state='normal')
                self.stop_button.configure(state='disabled')
                if data['failed']:
                    self.status.set('读取失败；已解析的数据保留。请根据错误提示处理后重试。')
                elif data['stopped']:
                    self.status.set('已停止，保留已解析数据。')
                elif data['offline']:
                    count = data['counts'].get('battles', 0)
                    self.status.set(f'导入完成：识别到 {count} 场对局，显示最后一场。' if count else '导入完成：没有对局初始化数据；可查看本号配装页。')

        self.root.after(100, self.poll)

    def close(self):
        if self.job and self.job.thread.is_alive():
            self.job.stop()
            self.root.withdraw()
            self.root.after(100, self.finish_close)
        else:
            self.root.destroy()

    def finish_close(self):
        if self.job.thread.is_alive():
            self.root.after(100, self.finish_close)
        else:
            self.root.destroy()


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
