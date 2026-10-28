"""Public GitHub release updates. Never updates user data or executes downloaded source."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse
import zipfile

REPO='yxp17326050531-spec/YinRepository'
API=f'https://api.github.com/repos/{REPO}/releases?per_page=100'
LIMIT=400*1024*1024

def version_key(value):
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(-calc-test)?',value)
    if not m:raise ValueError('不支持的版本号')
    return tuple(map(int,m.groups()[:3]))

def allowed_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):return False
    return ((p.hostname=='api.github.com' and p.path.startswith('/repos/'+REPO+'/')) or
            (p.hostname=='github.com' and p.path.startswith('/'+REPO+'/releases/download/')) or
            p.hostname=='release-assets.githubusercontent.com' or p.hostname=='objects.githubusercontent.com')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed_url(newurl):raise ValueError('更新下载重定向地址不受信任')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(url,path,maximum=LIMIT):
    if not allowed_url(url):raise ValueError('更新地址不属于本项目发行渠道')
    opener=urllib.request.build_opener(SafeRedirect())
    try:
        with opener.open(urllib.request.Request(url,headers={'User-Agent':'EtheriaAssistant-Updater','Accept':'application/vnd.github+json'}),timeout=30) as r,Path(path).open('wb') as out:
            size=0
            while block:=r.read(1024*1024):
                size+=len(block)
                if size>maximum:raise ValueError('更新文件超过大小限制')
                out.write(block)
    except Exception:
        Path(path).unlink(missing_ok=True);raise

def check(current,releases=None):
    if releases is None:
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'releases.json';download(API,p,4*1024*1024);releases=json.loads(p.read_text())
    choices=[]
    for release in releases:
        v=release.get('tag_name','').removeprefix('v')
        try:key=version_key(v)
        except ValueError:continue
        if release.get('draft') or v.endswith('-calc-test')!=current.endswith('-calc-test'):continue
        if not current.endswith('-calc-test') and release.get('prerelease'):continue
        if key<=version_key(current):continue
        assets={a['name']:a for a in release.get('assets',[])}
        if 'release.json' not in assets:continue
        candidates=[f'EtheriaAssistant-{v}-windows-x64.zip',f'EtheriaAssistant-{v}-windows-x64-portable.zip']
        name=next((n for n in candidates if n in assets),None)
        if name:choices.append((key,{'version':v,'asset':assets[name],'manifest':assets['release.json'],'notes':str(release.get('body') or '')[:3000]}))
    return max(choices,key=lambda row:row[0])[1] if choices else None

def install_root():
    root=os.environ.get('ETHERIA_PORTABLE_ROOT')
    if root:return Path(root).resolve()
    if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent
    return None

def extract_checked(archive,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist())>30000 or sum(i.file_size for i in z.infolist())>2*1024**3:raise ValueError('更新包解压大小异常')
        seen=set()
        for info in z.infolist():
            name=info.filename
            p=PurePosixPath(name)
            if '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name or not p.parts or p.parts[0]!='EtheriaAssistant':raise ValueError('更新包路径不安全')
            if stat.S_ISLNK(info.external_attr>>16):raise ValueError('更新包不允许链接')
            if name.casefold() in seen:raise ValueError('更新包有重复路径')
            seen.add(name.casefold())
            if any(part.lower().endswith(('.sqlite3','.db','.pcap','.pcapng')) or part.lower() in ('runtime.log','history.sqlite3-wal','history.sqlite3-shm') for part in p.parts):raise ValueError('更新包含用户数据')
        z.extractall(destination)
    bundle=destination/'EtheriaAssistant'
    if not (bundle/'EtheriaAssistant.exe').is_file() or not (bundle/'_internal').is_dir():raise ValueError('更新包缺少程序或运行库')
    if (bundle/'EtheriaAssistant.exe').read_bytes()[:2]!=b'MZ':raise ValueError('不是Windows程序')
    return bundle

def prepare(release,root):
    root=Path(root).resolve()
    if not (root/'EtheriaAssistant.exe').is_file():raise ValueError('请在完整EXE发行版中更新')
    task=Path(tempfile.mkdtemp(prefix='EtheriaUpdate-',dir=root.parent))
    try:
        manifest=task/'release.json';download(release['manifest']['browser_download_url'],manifest,1024*1024)
        m=json.loads(manifest.read_text())
        name=release['asset']['name']
        if m.get('version')!=release['version'] or m.get('file')!=name or not re.fullmatch('[0-9a-f]{64}',m.get('sha256','')):raise ValueError('更新清单版本或文件不匹配')
        archive=task/'update.zip';download(release['asset']['browser_download_url'],archive)
        with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=m['sha256']:raise ValueError('更新包校验失败')
        extract_checked(archive,task/'staged')
        # Worker runs from a complete independent copy, avoiding locked Python/Qt DLLs.
        worker=task/'worker';shutil.copytree(root,worker,ignore=shutil.ignore_patterns('*.sqlite3','*.sqlite3-*','*.pcap','*.pcapng','runtime.log*'))
        return task
    except Exception:
        shutil.rmtree(task,ignore_errors=True);raise

def wait_pid(pid,seconds=90):
    if os.name!='nt':raise RuntimeError('仅支持Windows应用更新')
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];api.OpenProcess.restype=ctypes.c_void_p
    api.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong];api.CloseHandle.argtypes=[ctypes.c_void_p]
    h=api.OpenProcess(0x100000,False,pid)
    if not h:
        if ctypes.get_last_error()==87:return
        raise OSError('不能确认旧程序已退出')
    try:
        if api.WaitForSingleObject(h,seconds*1000)!=0:raise TimeoutError('旧程序仍在运行，未替换文件')
    finally:api.CloseHandle(h)

def launch_worker(task,root):
    worker=Path(task)/'worker'
    args=['--update-worker',str(Path(task).resolve()),str(Path(root).resolve()),str(os.getpid()),str(os.getppid())]
    if os.environ.get('ETHERIA_PORTABLE_ROOT'):
        command=[str(worker/'_internal/python/pythonw.exe'),str(worker/'_internal/app/portable_bootstrap.py'),*args]
    else:command=[str(worker/'EtheriaAssistant.exe'),*args]
    return subprocess.Popen(command,cwd=worker,creationflags=0x00000008|0x00000200,close_fds=True)

def worker_main(task,root,pids):
    task=Path(task).resolve();root=Path(root).resolve();old=task/'previous';new=task/'staged/EtheriaAssistant'
    try:
        if task.parent!=root.parent or not task.name.startswith('EtheriaUpdate-') or not new.is_dir():raise ValueError('更新任务目录不正确')
        for pid in dict.fromkeys(pids):wait_pid(pid)
        root.rename(old)
        try:
            new.rename(root)
            env=dict(os.environ,ETHERIA_PORTABLE_ROOT=str(root),QT_QPA_PLATFORM='offscreen')
            report=task/'startup.json'
            subprocess.run([str(root/'EtheriaAssistant.exe'),'--smoke-test',str(report)],cwd=root,env=env,timeout=60,check=True)
            if not json.loads(report.read_text())['ok']:raise RuntimeError('新版启动检查失败')
        except Exception:
            if root.exists():root.rename(task/'failed-new')
            old.rename(root);raise
        subprocess.Popen([str(root/'EtheriaAssistant.exe')],cwd=root,env={**os.environ,'ETHERIA_PORTABLE_ROOT':str(root)})
        (task/'success.txt').write_text('Previous program is in previous/. User database was not replaced.')
        return 0
    except Exception as exc:
        (task/'update-error.txt').write_text(str(exc),encoding='utf-8')
        if os.name=='nt':ctypes.windll.user32.MessageBoxW(None,'更新未完成，旧版和数据库保留。\n'+str(exc),'伊瑟更新',0x10)
        return 1
