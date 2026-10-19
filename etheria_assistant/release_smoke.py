"""Frozen startup smoke check; always uses a new temporary archive."""
import json
from pathlib import Path
import tempfile
import traceback


def run(report):
    result={'ok':False};window=None;archive=None
    try:
        from PySide6.QtWidgets import QApplication
        from qt_app import MainWindow,VERSION
        from storage import Archive
        from core import load_mappings
        from artwork import catalogue,portrait
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            try:
                archive=Archive(tmp);window=MainWindow(archive);window.navigate(0);window.show();app.processEvents()
                if not load_mappings().get('heroes'):raise RuntimeError('Hero mapping missing')
                for kind in ('heroes','shells','matrices'):
                    names=catalogue().get(kind,{})
                    if not names or portrait(kind,next(iter(names)),24).isNull():raise RuntimeError('Artwork missing: '+kind)
                result={'ok':True,'version':VERSION,'check':'Qt startup, isolated archive, mappings and artwork'}
            finally:
                if window:window.close();app.processEvents()
                if archive:
                    for handler in archive.logger.handlers[:]:handler.close();archive.logger.removeHandler(handler)
    except Exception:result={'ok':False,'error':traceback.format_exc()}
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1
