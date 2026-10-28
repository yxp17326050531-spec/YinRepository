"""Mapping-only JSON presets and transactional, edit-safe import undo."""
import copy
import json
from datetime import datetime,timezone

CATEGORIES=('heroes','shell_configs','shell_effects','matrices','matrix_effects')
FORMAT='etheria-mapping-preset'


def validate_bundle(bundle):
    if not isinstance(bundle,dict) or set(bundle)!={'format','schema','name','mappings'}:raise ValueError('不是编号映射预设文件')
    if bundle['format']!=FORMAT or type(bundle['schema']) is not int or bundle['schema']!=1:raise ValueError('不支持的映射预设版本')
    if not isinstance(bundle['name'],str) or not 1<=len(bundle['name'].strip())<=100:raise ValueError('预设名称应为1–100字')
    maps=bundle['mappings']
    if not isinstance(maps,dict) or not set(maps)<=set(CATEGORIES):raise ValueError('映射分类不受支持')
    count=0
    for cat,rows in maps.items():
        if not isinstance(rows,dict):raise ValueError('映射内容应为编号字典')
        count+=len(rows)
        for identifier,value in rows.items():
            if not isinstance(identifier,str) or not identifier.isascii() or not identifier.isdecimal() or str(int(identifier))!=identifier or not 0<int(identifier)<2**64:raise ValueError('映射编号须为规范正整数')
            if cat in ('shell_effects','matrix_effects'):
                allowed={'name','confidence','threshold'} if cat=='matrix_effects' else {'name','confidence'}
                if not isinstance(value,dict) or not {'name'}<=set(value)<=allowed:raise ValueError('效果映射字段不正确')
                if 'confidence' in value and (not isinstance(value['confidence'],str) or len(value['confidence'])>100):raise ValueError('映射来源说明不正确')
                t=value.get('threshold')
                if t is not None and (type(t) is not int or not 1<=t<=999):raise ValueError('矩阵效果档位须为1–999或null')
                name=value['name']
            else:name=value
            if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('映射名称应为1–100字')
    if count>20000:raise ValueError('预设最多包含20000项映射')
    return copy.deepcopy(bundle)


def read_bundle(path):
    if path.stat().st_size>4*1024*1024:raise ValueError('映射文件不能超过4MiB')
    return validate_bundle(json.loads(path.read_text(encoding='utf-8-sig')))


class MappingPresets:
    def __init__(self,archive):self.archive=archive
    def snapshot(self,name):
        maps={}
        with self.archive.connect() as db:
            for row in db.execute('SELECT category,id,value FROM mappings'):
                if row['category'] in CATEGORIES:maps.setdefault(row['category'],{})[row['id']]=json.loads(row['value'])
        return validate_bundle({'format':FORMAT,'schema':1,'name':name,'mappings':maps})
    def presets(self):return self.archive.settings().get('mapping_presets',{})
    def save(self,bundle):
        bundle=validate_bundle(bundle);saved=self.presets();saved[bundle['name']]=bundle
        self.archive.save_settings({'mapping_presets':saved})
    def delete(self,name):
        saved=self.presets();saved.pop(name,None);self.archive.save_settings({'mapping_presets':saved})
    def preview(self,bundle,builtin):
        bundle=validate_bundle(bundle);counts={'new':0,'same':0,'conflict':0,'builtin_override':0}
        current={c:self.archive.custom_mappings(c) for c in CATEGORIES}
        for cat,rows in bundle['mappings'].items():
            for code,value in rows.items():
                if code in current[cat]:counts['same' if current[cat][code]==value else 'conflict']+=1
                else:
                    counts['new']+=1
                    if code in builtin.get(cat,{}) and builtin[cat][code]!=value:counts['builtin_override']+=1
        return counts
    def apply(self,bundle,overwrite=False):
        bundle=validate_bundle(bundle);changes=[]
        with self.archive.connect() as db:
            for cat,rows in bundle['mappings'].items():
                for code,value in rows.items():
                    row=db.execute('SELECT value FROM mappings WHERE category=? AND id=?',(cat,code)).fetchone()
                    before=json.loads(row['value']) if row else None
                    if before==value or (row is not None and not overwrite):continue
                    db.execute('INSERT OR REPLACE INTO mappings VALUES(?,?,?)',(cat,code,json.dumps(value,ensure_ascii=False)))
                    changes.append({'category':cat,'id':code,'before':before,'after':value})
            if changes:
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('mapping_import_undo',json.dumps(changes,ensure_ascii=False)))
                db.execute('INSERT INTO audit VALUES(?,?,?,?)',(datetime.now(timezone.utc).isoformat(),'import_mapping_preset',bundle['name'],json.dumps({'changed':len(changes)})))
        return len(changes)
    def undo(self):
        restored=0;skipped=0
        with self.archive.connect() as db:
            record=db.execute('SELECT value FROM settings WHERE key=?',('mapping_import_undo',)).fetchone()
            for change in json.loads(record['value']) if record else []:
                cat,code=change['category'],change['id']
                row=db.execute('SELECT value FROM mappings WHERE category=? AND id=?',(cat,code)).fetchone()
                if row is None or json.loads(row['value'])!=change['after']:skipped+=1;continue
                if change['before'] is None:db.execute('DELETE FROM mappings WHERE category=? AND id=?',(cat,code))
                else:db.execute('UPDATE mappings SET value=? WHERE category=? AND id=?',(json.dumps(change['before'],ensure_ascii=False),cat,code))
                restored+=1
            db.execute('DELETE FROM settings WHERE key=?',('mapping_import_undo',))
            db.execute('INSERT INTO audit VALUES(?,?,?,?)',(datetime.now(timezone.utc).isoformat(),'undo_mapping_import','',json.dumps({'restored':restored,'skipped':skipped})))
        return restored,skipped
