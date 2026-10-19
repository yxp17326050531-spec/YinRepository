"""Local inventory, explicit match labels and observed lineup statistics."""
import json
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from analytics import analyse, rank_statistics
from core import matrix_name, shell_config_name
from ui_components import FormDialog


RESULTS = {'未知':'unknown','A队胜':'A','B队胜':'B','平局':'draw'}
KINDS = ('未分类','BP排位','竞技场','练习/测试')


class CompanionFeatures:
    def name_cell_click(self,event):
        row=self.tree.identify_row(event.y)
        if row in self.unit_rows and self.tree.identify_column(event.x)=='#2':
            self.tree.selection_set(row);self.tree.focus(row)
            self.edit_hero_name(self.unit_rows[row])
            return 'break'

    def battle_double_click(self,event):
        if self.tree.identify_column(event.x)!='#2':self.edit_unit()
        return 'break'

    def edit_hero_name(self,unit=None):
        previous=getattr(self,'_hero_name_dialog',None)
        if previous is not None and previous.winfo_exists():
            previous.lift();return
        if unit is None:
            selected=self.tree.selection()
            if not selected or selected[0] not in self.unit_rows:
                messagebox.showinfo('先选择角色','点击表格中的角色名称，或先选择一名角色。');return
            unit=self.unit_rows[selected[0]]
        identifier=unit['hero_id']
        window=FormDialog(self.root,f'角色编号改名 · {identifier}')
        self._hero_name_dialog=window
        ttk.Label(window.content,text=f'精确角色编号：{identifier}',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(0,12))
        ttk.Label(window.content,text='名称会应用到该编号的所有当前和历史显示。不同皮肤编号可以分别维护。',wraplength=550,style='Hint.TLabel').pack(anchor='w',pady=(0,12))
        name=tk.StringVar(value=self.mappings['heroes'].get(str(identifier),''))
        entry=ttk.Combobox(window.content,textvariable=name,values=sorted(set(self.mappings['heroes'].values())))
        entry.pack(fill='x')
        ttk.Label(window.content,text='这是编号名称映射，统计仍按精确编号分别计数；不自动按同名合并皮肤。',wraplength=550,style='Hint.TLabel').pack(anchor='w',pady=12)
        def save():
            try:
                self.archive.set_mapping('heroes',identifier,name.get())
                self.mappings_changed()
                self.status.set(f'已保存角色映射：{identifier} → {name.get().strip()}')
                window.destroy()
            except Exception as exc:messagebox.showerror('保存失败',str(exc),parent=window)
        ttk.Button(window.actions,text='保存名称',command=save,style='Accent.TButton').pack(side='left')
        ttk.Button(window.actions,text='取消',command=window.destroy).pack(side='right')
        window.bind('<Control-Return>',lambda event:save());window.finish(entry)

    def select_history_page(self,event=None):
        self.history_tree.selection_set(self.history_tree.get_children())
        return 'break'

    def delete_history(self):
        selected=self.history_tree.selection()
        if not selected:
            messagebox.showinfo('先选择记录','可按Ctrl或Shift选择多场，Ctrl+A选择当前页。');return
        try:
            removed=set(self.archive.trash_battles(selected))
            if self.current_id in removed:
                self.current_id=None;self.raw_current=None;self.annotations={};self.browsing=False
                self.render_battle()
            if self.live_id in removed:self.live_id=None;self.live_data=None
            self.reload_history();self.refresh_statistics()
            self.status.set(f'已删除{len(removed)}场，不再参与统计；可点“恢复最近一批删除”撤销。')
        except Exception as exc:messagebox.showerror('删除失败',str(exc))

    def restore_history(self):
        try:
            restored=self.archive.restore_last_trash()
            self.reload_history();self.refresh_statistics()
            self.status.set(f'已恢复{len(restored)}场记录。' if restored else '没有可恢复的删除记录。')
        except Exception as exc:messagebox.showerror('恢复失败',str(exc))

    def create_data_tabs(self):
        saved = self.archive.latest_inventory()
        self.bag_snapshot = saved['data'] if saved else None
        self.gear_rows = {}
        page = ttk.Frame(self.notebook,padding=14)
        self.notebook.add(page,text='源器背包')
        ttk.Label(page,text='已收到的本号源器会自动保存；重新启动后可继续查看。',style='Hint.TLabel').pack(anchor='w',pady=(0,10))
        bar = ttk.Frame(page);bar.pack(fill='x',pady=(0,10))
        ttk.Label(bar,text='搜索矩阵、角色或编号').pack(side='left')
        self.gear_query = tk.StringVar()
        ttk.Entry(bar,textvariable=self.gear_query,width=24).pack(side='left',padx=8)
        ttk.Button(bar,text='导出库存 JSON',command=self.export_inventory).pack(side='right')
        self.gear_info = tk.StringVar()
        ttk.Label(page,textvariable=self.gear_info,style='Hint.TLabel').pack(anchor='w',pady=(0,8))
        self.gear_tree = self.make_tree(page,[('uid','源器编号',120),('level','等级',65),('matrix','矩阵',140),('points','贡献点数',90),('owner','装备关联',390),('attrs','属性状态',150)],height=9)
        self.gear_details = tk.Text(page,height=4,wrap='word',font=('Microsoft YaHei UI',10),relief='flat',padx=12,pady=10,bg='#edf2fa',fg='#425372')
        self.gear_details.pack(fill='x',pady=(10,0))
        self.gear_tree.bind('<<TreeviewSelect>>',self.show_gear_details)
        self.gear_query.trace_add('write',lambda *args:self.render_gear())
        self.render_gear()
        if self.bag_snapshot:
            self.inventory_rows = self.bag_snapshot.get('loadout_rows',[])
            self.inventory_status.set('已恢复上次保存的本号配装；新库存到达后更新。')
            self.render_inventory()

        page = ttk.Frame(self.notebook,padding=14)
        self.stats_tab = page
        self.notebook.add(page,text='战绩统计')
        ttk.Label(page,text='统计你捕获并标记的样本；不是全服数据。胜负暂由手动标记。',style='Hint.TLabel').pack(anchor='w',pady=(0,12))
        filters = ttk.Frame(page);filters.pack(fill='x',pady=(0,12))
        ttk.Label(filters,text='对局类型').pack(side='left')
        self.stats_kind = tk.StringVar(value='BP排位')
        kind_picker=ttk.Combobox(filters,textvariable=self.stats_kind,state='readonly',values=('BP排位','竞技场','全部已分类','未分类','练习/测试'),width=11)
        kind_picker.pack(side='left',padx=8)
        kind_picker.bind('<<ComboboxSelected>>',lambda event:self.refresh_statistics())
        ttk.Label(filters,text='统计分组').pack(side='left')
        self.stats_group = tk.StringVar()
        self.stats_group_picker = ttk.Combobox(filters,textvariable=self.stats_group,width=20)
        self.stats_group_picker.pack(side='left',padx=8)
        ttk.Button(filters,text='刷新统计',command=self.refresh_statistics,style='Accent.TButton').pack(side='left')
        ttk.Button(filters,text='导出分析数据集',command=self.export_dataset).pack(side='right')
        focus_bar=ttk.Frame(page);focus_bar.pack(fill='x',pady=(0,12))
        ttk.Label(focus_bar,text='关注角色').pack(side='left')
        self.stats_focus=tk.StringVar(value='全部角色')
        self.stats_focus_picker=ttk.Combobox(focus_bar,textvariable=self.stats_focus,state='readonly',width=24)
        self.stats_focus_picker.pack(side='left',padx=8)
        self.stats_focus_picker.bind('<<ComboboxSelected>>',lambda event:self.refresh_statistics())
        ttk.Label(focus_bar,text='统计视角').pack(side='left')
        self.stats_perspective=tk.StringVar(value='双方队伍')
        perspective_picker=ttk.Combobox(focus_bar,textvariable=self.stats_perspective,state='readonly',values=('双方队伍','仅己方'),width=9)
        perspective_picker.pack(side='left',padx=8)
        perspective_picker.bind('<<ComboboxSelected>>',lambda event:self.refresh_statistics())
        ttk.Label(focus_bar,text='榜单最少胜负样本').pack(side='left')
        self.stats_min=tk.StringVar(value='5')
        minimum=ttk.Spinbox(focus_bar,from_=1,to=100000,textvariable=self.stats_min,width=6,command=self.refresh_statistics)
        minimum.pack(side='left',padx=8)
        minimum.bind('<Return>',lambda event:self.refresh_statistics())
        self.stats_summary = tk.StringVar()
        ttk.Label(page,textvariable=self.stats_summary,font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(0,12))
        sections=ttk.Notebook(page);sections.pack(fill='both',expand=True)
        overview=ttk.Frame(sections,padding=4);against=ttk.Frame(sections,padding=4);together=ttk.Frame(sections,padding=4)
        sections.add(overview,text='角色概览');sections.add(against,text='对位胜率 · 低到高');sections.add(together,text='搭配胜率 · 高到低')
        self.stats_tree = self.make_tree(overview,[('hero','角色',125),('id','精确编号',100),('appear','出场队伍数',110),('rate','队伍出场率',100),('win','胜',55),('loss','负',55),('draw','平',55),('unknown','未知胜负',100),('n','胜率样本数',100),('wr','样本胜率',100)],height=8)
        columns=[('hero','角色',180),('other','对方角色',180),('appear','观测次数',90),('win','胜',55),('loss','负',55),('draw','平',55),('unknown','未知',65),('n','胜负样本数',110),('wr','整队胜率',110)]
        self.matchup_tree=self.make_tree(against,columns,height=8)
        self.pair_tree=self.make_tree(together,[(k,'搭配角色' if k=='other' else title,width) for k,title,width in columns],height=8)
        ttk.Label(page,text='出场率＝包含该角色的队伍数 ÷ 观测队伍总数；胜率＝胜 ÷（胜＋负）。平局、未知结果不计入胜率。',style='Hint.TLabel',wraplength=1120).pack(anchor='w',pady=(10,4))
        ttk.Label(page,text='对位/搭配是整队胜负，不代表单挑克制；角色变体按精确编号分别统计。“仅己方”会排除未选择对方队伍的记录。',style='Hint.TLabel',wraplength=1120).pack(anchor='w')
        actions=ttk.Frame(page);actions.pack(fill='x',pady=(10,0))
        ttk.Button(actions,text='查看结算观测',command=self.show_observations).pack(side='left')
        ttk.Button(actions,text='导出胜负验证资料',command=self.export_validation).pack(side='left',padx=8)
        self.observation_status = tk.StringVar(value='结算消息已保存，自动判断胜负尚待验证。')
        ttk.Label(actions,textvariable=self.observation_status,style='Hint.TLabel').pack(side='left',padx=10)
        self.refresh_statistics()

    def render_gear(self):
        snapshot = self.bag_snapshot
        self.gear_tree.delete(*self.gear_tree.get_children())
        self.gear_rows.clear()
        self.gear_details.configure(state='normal')
        self.gear_details.delete('1.0','end')
        self.gear_details.insert('1.0','点击源器查看已保存的原始属性项。主副属性、部位和单位尚未核对，暂不计算配装面板。')
        self.gear_details.configure(state='disabled')
        if not snapshot:
            self.gear_info.set('暂无库存。可导入原来的登录抓包，或从登录前开始监听。')
            return
        holders = {}
        for hero in snapshot.get('heroes',[]):
            name = self.mappings['heroes'].get(str(hero['hero_id']),f"角色 #{hero['hero_id']}")
            for field,label in [('normal_gear_uids','普通'),('arena_gear_uids','竞技候选')]:
                for uid in hero[field]:
                    holders.setdefault(uid,[]).append(f'{name}·{label}')
        query = self.gear_query.get().strip().lower()
        for row in snapshot.get('gear',[]):
            name = matrix_name(self.mappings,row['matrix']['id'])
            owner = ' / '.join(holders.get(row['uid'],[])) or '无已观测关联'
            text = f"{row['uid']} {row['config_id']} {name} {row['matrix']['id']} {owner}".lower()
            if query and query not in text:
                continue
            identity=str(row['uid'])
            self.gear_rows[identity]=row
            self.gear_tree.insert('','end',iid=identity,values=(row['uid'],row['level'],name,row['matrix']['points'],owner,f"{len(row['attributes_raw'])}项，待核对"))
        stamp=snapshot.get('capture_time')
        stamp=datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M') if stamp else '未知时间'
        self.gear_info.set(f"源器 {len(snapshot.get('gear',[]))} 件 · 智壳 {len(snapshot.get('shells',[]))} 个 · 当前显示 {len(self.gear_rows)} 件 · 采集 {stamp}；仅本次已收到的库存。")

    def show_gear_details(self,event=None):
        selected=self.gear_tree.selection()
        if not selected:return
        row=self.gear_rows[selected[0]]
        values='；'.join(f'{i+1}: {value} (0x{value:X})' for i,value in enumerate(row['attributes_raw']))
        text=f"实例 {row['uid']} · 配置 {row['config_id']} · 等级 {row['level']} · 标志原值 {row['flag_raw']}\n属性原值：{values}\n这些原值尚未转换为主副属性及最终面板，不能直接按战斗属性的公式解码。"
        self.gear_details.configure(state='normal');self.gear_details.delete('1.0','end');self.gear_details.insert('1.0',text);self.gear_details.configure(state='disabled')

    def write_json_dialog(self,data,filename):
        path=filedialog.asksaveasfilename(initialfile=filename,defaultextension='.json',filetypes=[('JSON','*.json')])
        if not path:return
        try:
            Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            self.status.set('已导出：'+Path(path).name)
        except Exception as exc:messagebox.showerror('导出失败',str(exc))

    def export_inventory(self):
        if not self.bag_snapshot:
            messagebox.showinfo('暂无库存','请先导入登录抓包或捕获登录数据。');return
        self.write_json_dialog(self.bag_snapshot,'etheria_local_inventory.json')

    def export_dataset(self):
        self.write_json_dialog(self.archive.dataset(),'etheria_analysis_dataset.json')

    def export_validation(self):
        self.write_json_dialog(self.archive.validation_dataset(),'etheria_result_validation.json')

    def edit_context(self,bid=None):
        bid=bid or self.current_id
        if not bid:
            messagebox.showinfo('先选择对局','请在对局页或历史中选择一场已保存的对局。');return
        context=self.archive.context(bid)
        record=self.archive.get(bid)
        original=record['original']
        window=FormDialog(self.root,'标记对局结果与统计类型')
        ttk.Label(window.content,text='按下面的阵容核对 A/B 队；不要按队伍顺序猜己方。',wraplength=560).pack(anchor='w',pady=(0,10))
        for team,units in original['teams'].items():
            names='、'.join(self.mappings['heroes'].get(str(u['hero_id']),f"角色 #{u['hero_id']}") for u in units)
            ttk.Label(window.content,text=f'{team}队：{names}',wraplength=560).pack(anchor='w',pady=4)
        winner=tk.StringVar(value=next(label for label,value in RESULTS.items() if value==context['winner']))
        opponent=tk.StringVar(value=record['opponent'])
        sample_kind=tk.StringVar(value=context['sample_kind'])
        group=tk.StringVar(value=context['dataset_group'])
        for label,value,options in [('对方队伍',opponent,('待选择','A 队','B 队')),('胜负',winner,tuple(RESULTS)),('对局类型',sample_kind,KINDS)]:
            ttk.Label(window.content,text=label).pack(anchor='w',pady=(12,3))
            ttk.Combobox(window.content,textvariable=value,state='readonly',values=options).pack(fill='x')
        ttk.Label(window.content,text='统计分组（可填赛季/版本/段位；留空表示未分组）').pack(anchor='w',pady=(12,3))
        entry=ttk.Entry(window.content,textvariable=group);entry.pack(fill='x')
        ttk.Label(window.content,text='测试抓包请标为“练习/测试”。统计默认只看 BP 排位；未知胜负不会按失败处理。',wraplength=560,style='Hint.TLabel').pack(anchor='w',pady=12)
        def save():
            try:
                self.archive.set_context(bid,RESULTS[winner.get()],sample_kind.get(),group.get())
                self.archive.set_opponent(bid,opponent.get())
                if self.current_id==bid:self.opponent.set(opponent.get())
                self.reload_history();self.refresh_statistics();window.destroy()
                self.status.set('已保存本场统计标记，原始对局数据保留。')
            except Exception as exc:messagebox.showerror('保存失败',str(exc),parent=window)
        ttk.Button(window.actions,text='保存标记',command=save,style='Accent.TButton').pack(side='left')
        ttk.Button(window.actions,text='取消',command=window.destroy).pack(side='right')
        window.bind('<Control-Return>',lambda event:save());window.finish(entry)

    def refresh_statistics(self):
        try:
            minimum=int(self.stats_min.get())
            if not 1<=minimum<=100000:raise ValueError()
        except ValueError:
            messagebox.showerror('样本数无效','榜单最少胜负样本应为1到100000之间的整数。');return
        dataset=self.archive.dataset()
        self.stats_group_picker['values']=['']+sorted({r['dataset_group'] for r in dataset['battles'] if r['dataset_group']})
        kind=self.stats_kind.get()
        kinds=('BP排位','竞技场') if kind=='全部已分类' else (kind,)
        result=analyse(dataset,self.mappings,kinds,self.stats_group.get().strip(),'own' if self.stats_perspective.get()=='仅己方' else 'both')
        def label(hero):return self.mappings['heroes'].get(str(hero),f'角色 #{hero}')+f' #{hero}'
        options=['全部角色']+[label(row['hero_id']) for row in result['heroes']]
        self.stats_focus_picker['values']=options
        if self.stats_focus.get() not in options:self.stats_focus.set('全部角色')
        focus=int(self.stats_focus.get().rsplit('#',1)[1]) if self.stats_focus.get()!='全部角色' else None
        self.stats_summary.set(f"观测对局 {result['eligible_matches']} 场    队伍样本 {result['team_samples']} 份    已标胜负 {result['decided_matches']} 场")
        self.stats_tree.delete(*self.stats_tree.get_children())
        for row in result['heroes']:
            if focus is not None and row['hero_id']!=focus:continue
            rate=f"{row['team_appearance_rate']:.1%}" if row['team_appearance_rate'] is not None else '—'
            win=f"{row['win_rate']:.1%}" if row['win_rate'] is not None else '—'
            self.stats_tree.insert('','end',values=(row['hero_name'],row['hero_id'],row['appearances'],rate,row['wins'],row['losses'],row['draws'],row['unknown'],row['decided'],win))
        for category,tree in [('matchups',self.matchup_tree),('cooccurrences',self.pair_tree)]:
            tree.delete(*tree.get_children())
            for row in rank_statistics(result,category,focus,minimum):
                if category=='matchups':left,right=row['hero_id'],row['opponent_id']
                else:
                    left,right=row['hero_ids']
                    if focus==right:left,right=right,left
                tree.insert('','end',values=(label(left),label(right),row['appearances'],row['wins'],row['losses'],row['draws'],row['unknown'],row['decided'],f"{row['win_rate']:.1%}"))

    def show_observations(self):
        window=FormDialog(self.root,'结算观测 · 最近300条')
        ttk.Label(window.content,text='结算对应的胜负尚未确认。打完后标记真实胜方并导出胜负验证资料，便于核对。',wraplength=980,style='Hint.TLabel').pack(anchor='w',pady=(0,10))
        tree=self.make_tree(window.content,[('time','结算时间',180),('battle','初始化时间线索',180),('state','解析状态',450)],height=10)
        for row in self.archive.observations('settlement'):
            data=row['data']
            stamp=datetime.fromtimestamp(row['capture_time']).strftime('%m-%d %H:%M:%S') if row['capture_time'] else '未知'
            linked=data.get('battle_capture_time')
            battle=datetime.fromtimestamp(linked).strftime('%m-%d %H:%M:%S') if linked is not None else '未收到可关联的初始化'
            tree.insert('','end',values=(stamp,battle,'结算已记录；胜方仍待核对，不计为失败'))
        ttk.Button(window.actions,text='关闭',command=window.destroy).pack(side='right');window.finish()
