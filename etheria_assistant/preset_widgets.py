"""Native Qt mapping and score preset managers. All imports preview before application."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
                              QLineEdit,QPlainTextEdit,QMessageBox,QFileDialog,QTabWidget,QWidget)
from core import load_mappings
from mapping_presets import MappingPresets,read_bundle
from gear_scoring import default_rules,validate_rules,load_rules


def plain(text):
    w=QLabel(text);w.setTextFormat(Qt.TextFormat.PlainText);w.setWordWrap(True);return w


def action(text,fn,layout):
    b=QPushButton(text);layout.addWidget(b);b.clicked.connect(lambda checked=False:guard(b,fn));return b


def guard(widget,fn):
    try:fn()
    except Exception as exc:QMessageBox.warning(widget,'操作未完成',str(exc))


def write_file(parent,bundle,filename):
    path,_=QFileDialog.getSaveFileName(parent,'导出预设',filename,'JSON (*.json)')
    if path:Path(path).write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')


class MappingPresetDialog(QDialog):
    def __init__(self,archive,changed,parent=None):
        super().__init__(parent);self.store=MappingPresets(archive);self.changed=changed
        self.setWindowTitle('编号映射预设');self.resize(760,560)
        root=QVBoxLayout(self);root.addWidget(plain('仅分享自定义编号，不包含战绩、昵称、抓包或计算器数据。删除预设只删除保存的模板，不移除已应用编号。'))
        self.list=QComboBox();root.addWidget(self.list);self.list.currentIndexChanged.connect(self.show_selected)
        row=QHBoxLayout();root.addLayout(row);self.name=QLineEdit();self.name.setPlaceholderText('预设名称');row.addWidget(self.name,1)
        action('保存当前自定义编号',self.save_current,row)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);root.addWidget(self.preview,1)
        row=QHBoxLayout();root.addLayout(row)
        action('导入文件',self.import_file,row);action('导出选中预设',self.export_file,row)
        action('应用预设',self.apply_selected,row);action('删除预设',self.delete_selected,row)
        row=QHBoxLayout();root.addLayout(row);action('撤销最近一次应用',self.undo,row);row.addStretch();action('关闭',self.accept,row)
        self.refresh()
    def refresh(self,selected=''):
        self.list.blockSignals(True);self.list.clear();self.list.addItems(sorted(self.store.presets()));self.list.setCurrentText(selected)
        self.list.blockSignals(False);self.show_selected()
    def selected(self):
        bundle=self.store.presets().get(self.list.currentText())
        if bundle is None:raise ValueError('请先保存或导入预设')
        return bundle
    def show_selected(self):
        bundle=self.store.presets().get(self.list.currentText())
        if not bundle:self.preview.setPlainText('尚无预设。可保存当前自定义编号，或导入其他用户分享的JSON文件。');return
        self.name.setText(bundle['name']);counts=self.store.preview(bundle,load_mappings())
        self.preview.setPlainText(f"新增 {counts['new']} · 相同 {counts['same']} · 自定义冲突 {counts['conflict']} · 将覆盖内置默认 {counts['builtin_override']}\n\n"+json.dumps(bundle['mappings'],ensure_ascii=False,indent=2))
    def save_bundle(self,bundle):
        if bundle['name'] in self.store.presets() and QMessageBox.question(self,'同名预设','覆盖已保存的同名预设？')!=QMessageBox.StandardButton.Yes:return
        self.store.save(bundle);self.refresh(bundle['name'])
    def save_current(self):self.save_bundle(self.store.snapshot(self.name.text().strip()))
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'导入映射预设','','JSON (*.json)')
        if path:self.save_bundle(read_bundle(Path(path)))
    def export_file(self):write_file(self,self.selected(),'etheria-mapping-preset.json')
    def apply_selected(self):
        bundle=self.selected();c=self.store.preview(bundle,load_mappings())
        d=QDialog(self);d.setWindowTitle('应用前预览');root=QVBoxLayout(d)
        root.addWidget(plain(f"新增 {c['new']} · 相同 {c['same']} · 自定义冲突 {c['conflict']} · 覆盖内置默认 {c['builtin_override']}\n不会删除文件中未包含的本地编号。"))
        policy=QComboBox();policy.addItems(['保留本地自定义冲突项（默认）','用预设覆盖冲突项']);root.addWidget(policy)
        row=QHBoxLayout();root.addLayout(row);action('取消',d.reject,row);action('确认应用',d.accept,row)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        n=self.store.apply(bundle,policy.currentIndex()==1);self.changed();self.show_selected()
        QMessageBox.information(self,'应用完成',f'已更新 {n} 项编号，可撤销最近一次应用。')
    def delete_selected(self):
        bundle=self.selected()
        if QMessageBox.question(self,'删除预设','只删除此模板，已应用编号保留。继续？')==QMessageBox.StandardButton.Yes:self.store.delete(bundle['name']);self.refresh()
    def undo(self):
        restored,skipped=self.store.undo();self.changed();self.show_selected()
        QMessageBox.information(self,'撤销结果',f'恢复 {restored} 项；跳过应用后已被修改或删除的 {skipped} 项。')


class ScoringPresetDialog(QDialog):
    def __init__(self,archive,current,selected,parent=None):
        super().__init__(parent);self.archive=archive;self.selected_callback=selected;self.setWindowTitle('源器评分预设');self.resize(820,660)
        root=QVBoxLayout(self);root.addWidget(plain('初版规则可调整。属性参考上限、倾向门槛、速度曲线及其他矩阵50%折扣为暂定；固定值折算和已确认矩阵规则已录入。导入预设后需点击“使用选中预设”。'))
        self.list=QComboBox();root.addWidget(self.list);self.list.currentIndexChanged.connect(self.show_selected)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        self.summary=QPlainTextEdit();self.summary.setReadOnly(True);self.tabs.addTab(self.summary,'规则说明')
        self.editor=QPlainTextEdit();self.tabs.addTab(self.editor,'高级参数 / 另存预设')
        row=QHBoxLayout();root.addLayout(row)
        action('保存编辑内容',self.save_editor,row);action('导入文件',self.import_file,row);action('导出预设',self.export_file,row);action('删除预设',self.delete_selected,row)
        row=QHBoxLayout();root.addLayout(row);action('使用选中预设',self.use_selected,row);row.addStretch();action('关闭',self.accept,row)
        self.refresh(current['name'])
    def presets(self):return self.archive.settings().get('gear_scoring_presets',{})
    def refresh(self,name=''):
        self.list.blockSignals(True);self.list.clear();self.list.addItem('内置初版',None)
        for key in sorted(self.presets()):self.list.addItem(key,key)
        i=self.list.findData(name);self.list.setCurrentIndex(max(0,i));self.list.blockSignals(False);self.show_selected()
    def selected(self):return default_rules() if self.list.currentData() is None else validate_rules(self.presets()[self.list.currentData()])
    def show_selected(self):
        rules=self.selected();self.editor.setPlainText(json.dumps(rules,ensure_ascii=False,indent=2))
        s=rules['speed'];self.summary.setPlainText(
            f"{rules['name']} · {rules['revision']}\n\n仅副属性计分，不修改原始数据、不表示实际伤害。\n"
            f"属性得分 = 等效数值 ÷ 参考值 × {rules['attribute_scale']} × 用途权重。\n"
            f"用途倾向：有效属性小计至少 {rules['minimum_score']}，至少 {rules['minimum_attributes']} 类有效属性达到参考值的{rules['meaningful_fraction']*100:g}%，并命中核心属性。\n"
            f"固定生命/攻击/防御分别除以 {rules['flat_conversion']['4']:g}/{rules['flat_conversion']['8']:g}/{rules['flat_conversion']['12']:g}，直接作为百分比计分。\n\n"
            f"速度仅按实际数值评分，不使用强化次数。显示14–16速为高速候选，17速起为一速。\n"
            f"一速 =（速度曲线基础分 + 最多{s['secondary_bonus_cap']:g}分添头）×矩阵系数×点数系数。\n"
            f"第一档 {s['top']} ×{s['top_factor']:g}\n第二档 {s['second']} ×{s['second_factor']:g}\n其他已知矩阵 ×{s['other_factor']:g}（暂定）\n"
            f"普通2点 ×{s['two_points_factor']:g}；已确认8件套2点与3点均×1。\n8件套：{s['eight_piece']}\n\n"
            '输出和辅助同样应用2点折扣及8件套例外，但不沿用一速矩阵偏好；未判定主属性、部位及整套配装兼容性。\n'
            '未知副属性不计最终分；账号按源器UID去重，每件只取最高用途分。库存总分可能混用同一件的配装用途，不代表同时可组出的队伍。')
    def save_rules(self,rules):
        rules=validate_rules(rules);saved=self.presets()
        if rules['name'] in saved and QMessageBox.question(self,'覆盖预设','更新同名评分预设？')!=QMessageBox.StandardButton.Yes:return
        saved[rules['name']]=rules;self.archive.save_settings({'gear_scoring_presets':saved});self.refresh(rules['name'])
    def save_editor(self):self.save_rules(json.loads(self.editor.toPlainText()))
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'导入评分预设','','JSON (*.json)')
        if path:self.save_rules(load_rules(Path(path)))
    def export_file(self):write_file(self,self.selected(),'etheria-scoring-preset.json')
    def delete_selected(self):
        name=self.list.currentData()
        if name is None:raise ValueError('内置预设不可删除，可另存修改版')
        if QMessageBox.question(self,'删除预设','删除保存的模板？当前已使用的规则仍保留。')!=QMessageBox.StandardButton.Yes:return
        saved=self.presets();saved.pop(name,None);self.archive.save_settings({'gear_scoring_presets':saved});self.refresh()
    def use_selected(self):self.selected_callback(self.selected());self.accept()
