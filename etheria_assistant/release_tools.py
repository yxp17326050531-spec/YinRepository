"""Local Windows release build and publication; no cloud runner or driver installer."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
REPOSITORY='yxp17326050531-spec/YinRepository'
RUNTIME_DATA=('mappings.json','hero_catalogue.json','RELEASE_README.md','THIRD_PARTY_NOTICES.md')
FORBIDDEN={'mapping_evidence.json','VALIDATION.md','RESULT_VALIDATION.md','RESULT_CANDIDATES.json','runtime.log'}


def version():
    for node in ast.parse((ROOT/'qt_app.py').read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Application version not found')


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def forbidden(path):
    p=Path(path);name=p.name.lower()
    return (p.name in FORBIDDEN or name.startswith(('runtime.log','npcap','winpcap'))
            or name in ('packet.dll','wpcap.dll') or p.suffix.lower() in ('.db','.sqlite3','.pcap','.pcapng','.sys')
            or '.sqlite3-' in name or any(x in ('.venv','.build-venv','.git','__pycache__') for x in p.parts))


def capture_files(directory):
    """Require an explicit reviewed, hashed user-mode runtime, never driver files."""
    directory=Path(directory)
    manifest=json.loads((directory/'capture_manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('version') or not manifest.get('source_url','').startswith('https://'):
        raise ValueError('Capture manifest requires version and corresponding source_url')
    files=manifest.get('files',{})
    if not {'dumpcap.exe','COPYING.txt','SOURCE.txt'} <= set(files):
        raise ValueError('Capture runtime requires dumpcap.exe, COPYING.txt and SOURCE.txt')
    selected=[]
    for name,digest in files.items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or forbidden(relative):
            raise ValueError('Capture file not allowed: '+name)
        file=directory/relative
        if not file.resolve().is_relative_to(directory.resolve()) or sha256(file)!=digest:
            raise ValueError('Capture file hash/path mismatch: '+name)
        if file.suffix.lower() in ('.exe','.dll'):
            with file.open('rb') as stream:
                if stream.read(2)!=b'MZ':raise ValueError('Expected Windows x64 runtime: '+name)
                stream.seek(60);offset=struct.unpack('<I',stream.read(4))[0];stream.seek(offset)
                if stream.read(4)!=b'PE\0\0' or stream.read(2)!=b'\x64\x86':raise ValueError('Expected Windows x64 runtime: '+name)
            if file.suffix.lower()=='.exe' and name!='dumpcap.exe':raise ValueError('Unexpected capture executable: '+name)
        selected.append(file)
    return selected+[directory/'capture_manifest.json']


def runtime_files(directory):
    """Refuse private evidence and drivers even if a build hook copied them."""
    root=Path(directory);files=sorted(p for p in root.rglob('*') if p.is_file())
    if not files:raise ValueError('Empty release directory')
    for file in files:
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()) or forbidden(file.relative_to(root)):
            raise ValueError('Release contains an excluded file: '+str(file.relative_to(root)))
    return files


def package(directory,output,release_version,commit):
    directory=Path(directory);output=Path(output);files=runtime_files(directory)
    if not (directory/'EtheriaAssistant.exe').is_file():raise ValueError('Windows executable missing')
    output.mkdir(parents=True,exist_ok=True)
    name=f'EtheriaAssistant-{release_version}-windows-x64.zip';archive=output/name
    # Build a new archive and replace only after it is complete.
    temporary=output/(name+'.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for file in files:z.write(file,Path('EtheriaAssistant')/file.relative_to(directory))
        temporary.replace(archive)
    finally:
        if temporary.exists():temporary.unlink()
    manifest={'version':release_version,'commit':commit,'file':name,'sha256':sha256(archive),'platform':'windows-x64'}
    (output/'release.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(manifest['sha256']+'  '+name+'\n',encoding='utf-8')
    return archive


def build(with_capture=False):
    if sys.platform!='win32' or struct.calcsize('P')!=8:
        raise RuntimeError('Build on 64-bit Windows Python. Linux cannot create a Windows EXE.')
    # Publication is tied to a reviewed commit; reject local edits and untracked source.
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=subprocess.check_output(['git','status','--porcelain','--','.'],cwd=ROOT,text=True).strip()
    if dirty:raise RuntimeError('Commit or stash local project changes before creating a release.')
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    if with_capture:
        capture_files(ROOT/'vendor'/'dumpcap');env['ETHERIA_BUNDLE_DUMPCAP']='1'
    else:env.pop('ETHERIA_BUNDLE_DUMPCAP',None)
    subprocess.run([sys.executable,'-m','unittest','discover','-v'],cwd=ROOT,env=env,check=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','EtheriaAssistant.spec'],cwd=ROOT,env=env,check=True)
    bundle=ROOT/'dist'/'EtheriaAssistant'
    for name in ('RELEASE_README.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name,bundle/name)
    # Clean-room app startup uses only a temporary database, not the user's profile.
    with tempfile.TemporaryDirectory() as tmp:
        report=Path(tmp)/'smoke.json'
        subprocess.run([str(bundle/'EtheriaAssistant.exe'),'--smoke-test',str(report)],cwd=bundle,env=env,check=True,timeout=60)
        if not json.loads(report.read_text(encoding='utf-8'))['ok']:raise RuntimeError('Frozen startup failed')
    archive=package(bundle,ROOT/'release',version(),commit)
    shutil.copy2(ROOT/'RELEASE_NOTES.md',archive.parent/'RELEASE_NOTES.md')
    print('Release ready:',archive)
    return archive


def publish():
    """Run on the owner's signed-in Windows machine using their GitHub CLI."""
    if not shutil.which('gh'):raise RuntimeError('Install GitHub CLI and run gh auth login first: https://cli.github.com/')
    output=ROOT/'release';m=json.loads((output/'release.json').read_text(encoding='utf-8'))
    archive=output/m['file']
    if m['version']!=version() or archive.parent.resolve()!=output.resolve() or sha256(archive)!=m['sha256']:
        raise ValueError('Release version or checksum mismatch; build again')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if m['commit']!=head:raise ValueError('Source changed since build; build again')
    subprocess.run(['gh','auth','status'],check=True)
    tag='v'+m['version']
    # Existing releases/assets are never overwritten.
    exists=subprocess.run(['gh','release','view',tag,'--repo',REPOSITORY],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if exists.returncode==0:raise ValueError('Release already exists: '+tag)
    ref=subprocess.run(['gh','api',f'repos/{REPOSITORY}/git/ref/tags/{tag}'],capture_output=True,text=True)
    if ref.returncode==0:raise ValueError('Tag already exists; do not bind a new build to an old tag: '+tag)
    if '404' not in ref.stderr:raise RuntimeError('Could not verify that the release tag is unused: '+ref.stderr.strip())
    subprocess.run(['gh','release','create',tag,str(archive),str(output/'SHA256SUMS.txt'),str(output/'release.json'),
                    '--repo',REPOSITORY,'--target',m['commit'],'--title',m['version']+' Windows',
                    '--notes-file',str(output/'RELEASE_NOTES.md')],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('build','publish'))
    parser.add_argument('--with-capture',action='store_true',help='Include only a reviewed vendor/dumpcap runtime')
    args=parser.parse_args()
    try:
        if args.command=='build':build(args.with_capture)
        else:publish()
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print('Release failed:',exc,file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
