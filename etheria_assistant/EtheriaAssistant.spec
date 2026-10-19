# Windows one-folder build. Run on Windows with PyInstaller installed.
from pathlib import Path

project = Path(SPECPATH)
datas = [(str(project / name), '.') for name in (
    'mappings.json', 'hero_catalogue.json', 'mapping_evidence.json',
    'RESULT_CANDIDATES.json', 'README.md', 'STATISTICS_PLAN.md',
    'SHARING_AND_UI.md', 'RESULT_VALIDATION.md', 'MAPPING_NOTES.md',
    'VALIDATION.md', 'MIGRATION.md', 'THIRD_PARTY_NOTICES.md')]
binaries = []

# Optional reviewed capture runtime. No driver or third-party executable is
# downloaded automatically. Supply matching runtime files and their notices.
capture = project / 'vendor' / 'dumpcap'
if capture.is_dir():
    for file in capture.rglob('*'):
        if file.is_file():
            target = str(Path('vendor/dumpcap') / file.relative_to(capture).parent)
            (binaries if file.suffix.lower() in ('.exe', '.dll') else datas).append((str(file), target))

a = Analysis([str(project / 'app.py')], pathex=[str(project)],
             binaries=binaries, datas=datas, hiddenimports=[],
             hookspath=[], runtime_hooks=[], excludes=['tkinter', 'PySide6.QtQml', 'PySide6.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='EtheriaAssistant', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                     name='EtheriaAssistant')
