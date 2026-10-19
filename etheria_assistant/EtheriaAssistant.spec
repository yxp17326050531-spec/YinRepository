# Windows one-folder release. Runtime resources are an explicit allowlist.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

project = Path(SPECPATH)
sys.path.insert(0, str(project))
from release_tools import RUNTIME_DATA, capture_files

datas = [(str(project / name), '.') for name in RUNTIME_DATA]
datas.append((str(project / 'assets'), 'assets'))
for dependency in ('PySide6-Essentials', 'shiboken6', 'PyInstaller'):
    datas += copy_metadata(dependency)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.is_file():
    datas.append((str(python_license), 'licenses/Python'))
if (project / 'licenses').is_dir():
    datas.append((str(project / 'licenses'), 'licenses'))

# Opt-in: preserve reviewed files byte-for-byte; do not let dependency discovery
# pick up Npcap DLLs or a driver installer from the build machine.
if os.environ.get('ETHERIA_BUNDLE_DUMPCAP') == '1':
    capture = project / 'vendor' / 'dumpcap'
    for file in capture_files(capture):
        target = str(Path('vendor/dumpcap') / file.relative_to(capture).parent)
        datas.append((str(file), target))

a = Analysis([str(project / 'app.py')], pathex=[str(project)],
             binaries=[], datas=datas, hiddenimports=['release_smoke'],
             hookspath=[], runtime_hooks=[], excludes=['tkinter', 'PySide6.QtQml', 'PySide6.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='EtheriaAssistant', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                     name='EtheriaAssistant')
