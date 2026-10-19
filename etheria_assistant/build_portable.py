"""Assemble Windows x64 app-local binaries on any host; not a Windows test claim."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile
from release_tools import ROOT,forbidden,sha256,version

INPUTS={
 'python-3.14.8-embed-amd64.zip':'a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310',
 'pyside6_essentials-6.12.0-cp310-abi3-win_amd64.whl':'c9a95102aa23c1f86516a30d5a9be37552d324eee7e567eb7508973f1218cb42',
 'shiboken6-6.12.0-cp310-abi3-win_amd64.whl':'a1906cb8116869178c64b6bab52623bbc8b4ceed7b30bfc3c9aa0f6e67f6438e',
}


def extract(source,destination):
    with zipfile.ZipFile(source) as z:
        for info in z.infolist():
            if not (destination/info.filename).resolve().is_relative_to(destination.resolve()):raise ValueError('Unsafe archive member')
        for info in z.infolist():
            if '__pycache__' not in Path(info.filename).parts and not info.filename.endswith('.pyc'):
                z.extract(info,destination)


def local_modules(root=ROOT):
    seen=set();todo=['app']
    while todo:
        name=todo.pop();path=root/(name+'.py')
        if name in seen or not path.is_file():continue
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Import):todo += [x.name.split('.')[0] for x in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module:todo.append(node.module.split('.')[0])
    return sorted(seen)


def pe_info(path):
    with Path(path).open('rb') as f:
        if f.read(2)!=b'MZ':raise ValueError('Not a Windows executable')
        f.seek(60);offset=struct.unpack('<I',f.read(4))[0];f.seek(offset)
        if f.read(4)!=b'PE\0\0':raise ValueError('Invalid PE signature')
        machine=struct.unpack('<H',f.read(2))[0];f.seek(offset+24+68)
        return machine,struct.unpack('<H',f.read(2))[0]


def compile_launcher(inputs):
    module=importlib.util.find_spec('ziglang')
    if module is None:raise RuntimeError('Install build-only ziglang==0.14.1')
    headers=Path(module.origin).parent/'lib'/'libc'/'include'/'any-windows-any'
    target=inputs/'EtheriaAssistant.exe'
    subprocess.run([sys.executable,'-m','ziglang','cc','-target','x86_64-windows-gnu','-nostdlib',
                    '-fno-stack-protector','-fno-builtin','-isystem',str(headers),'-D_WIN32_WINNT=0x0A00',
                    '-Os','-s','-Wl,--entry,mainCRTStartup','-Wl,--subsystem,windows',
                    str(ROOT/'portable_launcher.c'),'-o',str(target),'-lkernel32','-luser32'],check=True)
    if pe_info(target)!=(0x8664,2):raise ValueError('Launcher must be native Windows x64 GUI')
    return target


def prune_runtime(packages,archives):
    """Resolve native dependencies from immutable wheel inventories, not directory scans."""
    import pefile
    native={};by_name={};handles=[]
    try:
        for archive in archives:
            z=zipfile.ZipFile(archive);handles.append(z)
            for name in z.namelist():
                if Path(name).suffix.lower() in ('.exe','.dll','.pyd'):
                    native[name]=z
                    by_name.setdefault(Path(name).name.lower(),[]).append(name)
        pending=[]
        for name in native:
            base=Path(name).name.lower()
            if name.startswith('shiboken6/') or base in ('qtcore.pyd','qtgui.pyd','qtwidgets.pyd','pyside6.abi3.dll'):
                pending.append(name)
            if name.startswith('PySide6/plugins/') and (base in ('qwindows.dll','qoffscreen.dll','qminimal.dll','qjpeg.dll','qico.dll','qgif.dll','qwebp.dll') or name.startswith('PySide6/plugins/styles/')):
                pending.append(name)
        keep=set()
        while pending:
            name=pending.pop()
            if name in keep:continue
            keep.add(name)
            with pefile.PE(data=native[name].read(name),fast_load=True) as pe:
                pe.parse_data_directories(directories=[1,13])
                for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[])+getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[]):
                    pending.extend(by_name.get(entry.dll.decode().lower(),[]))
        for name,z in native.items():
            target=packages/name
            if name in keep:
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
            elif target.exists():target.unlink()
        for name in ('qml','include','typesystems','glue'):
            directory=packages/'PySide6'/name
            if directory.is_dir() and not any(n.startswith('PySide6/'+name+'/') for n in keep):shutil.rmtree(directory)
    finally:
        for z in handles:z.close()


def assemble(inputs,output):
    inputs=Path(inputs).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    for name,digest in INPUTS.items():
        if sha256(inputs/name)!=digest:raise ValueError('Official input SHA256 mismatch: '+name)
    launcher=compile_launcher(inputs)
    bundle=output/'EtheriaAssistant'
    if bundle.exists():raise ValueError('Use a new output directory; never merge releases')
    runtime=bundle/'_internal'/'python';packages=bundle/'_internal'/'site-packages';source=bundle/'_internal'/'app'
    for directory in (runtime,packages,source):directory.mkdir(parents=True,exist_ok=True)
    extract(inputs/'python-3.14.8-embed-amd64.zip',runtime)
    for name in INPUTS:
        if name.endswith('.whl'):extract(inputs/name,packages)
    prune_runtime(packages,[inputs/name for name in INPUTS if name.endswith('.whl')])
    # Isolated app-local paths: no dependency on a system Python installation.
    (runtime/'python314._pth').write_text('python314.zip\n.\n../site-packages\n../app\nimport site\n',encoding='utf-8')
    for name in local_modules()+['portable_bootstrap']:
        shutil.copy2(ROOT/(name+'.py'),source/(name+'.py'))
    for name in ('mappings.json','hero_catalogue.json'):shutil.copy2(ROOT/name,source/name)
    shutil.copytree(ROOT/'assets',source/'assets')
    shutil.copytree(ROOT/'licenses',bundle/'licenses')
    for name in ('RELEASE_README.md','THIRD_PARTY_NOTICES.md'):shutil.copy2(ROOT/name,bundle/name)
    shutil.copy2(runtime/'LICENSE.txt',bundle/'licenses'/'Python-LICENSE.txt')
    shutil.copy2(launcher,bundle/'EtheriaAssistant.exe')
    readme='''伊瑟 · 对局助手 2.10.0 — Windows x64 便携版

完整解压ZIP后，双击EtheriaAssistant.exe。无需安装Python。
必须保留_internal目录，不要只拷EXE，也不要在压缩包中直接运行。

本包使用Windows官方嵌入式Python、PySide6运行库和原生GUI启动器。
不写入系统Python，不需要管理员权限安装本程序。
历史和映射仍在%LOCALAPPDATA%\\EtheriaAssistant。
本包更新时关闭程序，完整解压到新目录即可，不混用旧_internal。

实时监听仍需电脑已有Wireshark/dumpcap与Npcap。设置页有官方安装说明；离线导入无需驱动。
Windows EXE已跨编译，发布包包含Windows运行库。兼容层启动检查不等于Windows实机验证。
异常启动时查看%LOCALAPPDATA%\\EtheriaAssistant\\startup-error.log。
'''
    (bundle/'先看这里.txt').write_text(readme,encoding='utf-8-sig')
    return finalize_bundle(bundle,output)


def finalize_bundle(bundle,output):
    bundle=Path(bundle);output=Path(output)
    def members():
        return sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='BUILD_MANIFEST.json'
                      and not any(part.startswith('.') for part in p.relative_to(bundle).parts))
    paths=members()
    for path in paths:
        if forbidden(path.relative_to(bundle)):raise ValueError('Excluded release member: '+str(path))
    manifest={'version':version(),'format':'windows-x64-app-local-python','python':'3.14.8','pyside':'6.12.0',
              'windows_hardware_tested':False,'official_input_sha256':INPUTS,
              'files':{p.relative_to(bundle).as_posix():sha256(p) for p in paths}}
    manifest_path=bundle/'BUILD_MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    archive=output/f'EtheriaAssistant-{version()}-windows-x64-portable.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in paths+[manifest_path]:z.write(path,Path('EtheriaAssistant')/path.relative_to(bundle))
    (output/'SHA256SUMS.txt').write_text(sha256(archive)+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'sha256':sha256(archive),'launcher_pe':pe_info(bundle/'EtheriaAssistant.exe')},indent=2))
    return archive


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();assemble(args.inputs,args.output)

if __name__=='__main__':main()
