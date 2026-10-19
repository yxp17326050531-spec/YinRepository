"""UI-independent capture worker and presentation helpers."""
from __future__ import annotations
import os, shutil, subprocess, sys, threading
from pathlib import Path
from core import Engine, packets
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


def imprint_text(unit):
    names=list(dict.fromkeys(item['name'] for item in unit.get('imprints',[])))
    return '刻影：'+(' / '.join(names) if names else '待识别')


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
        threshold=matrix.get('threshold')
        effect=f'{threshold}点效果' if threshold is not None else '效果 · 档位待确认'
        label = f"{matrix['name']} {effect}（{status}）"
        if label not in labels:
            labels.append(label)
    return '、'.join(labels) if labels else '完整矩阵未知'


class CaptureJob:
    def __init__(self, emit, port, mappings, archive=None, capture_context='live'):
        self.emit = emit
        self.archive = archive
        self.source = ''
        self.engine = Engine(self.on_event, port, mappings,capture_context)
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
                    if self.archive:
                        first = next(packets(stream), None)
                        stream.seek(0)
                        # Never seed an older replay with a later inventory state.
                        saved = self.archive.latest_inventory(before=first[0]) if first else None
                        if saved:
                            self.engine.inventory.restore(saved['data'])
                    self.engine.read(stream, self.stop_event)
            else:
                if self.archive:
                    saved = self.archive.latest_inventory()
                    if saved:
                        self.engine.inventory.restore(saved['data'])
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
            self.engine.finish_capture('采集失败，尚未收到结算' if failed else '采集已停止，尚未收到结算')
            if self.archive:
                try:self.archive.save_settings({'last_capture_diagnostics':self.engine.diagnostics()})
                except Exception as exc:self.emit('storage_error','诊断保存失败：'+str(exc))
            self.emit('done', {'stopped': self.stop_event.is_set(), 'offline': bool(path),
                               'failed': failed, 'counts': dict(self.engine.counts)})
            if self.archive:
                self.archive.logger.info('done failed=%s counts=%s', failed, dict(self.engine.counts))
