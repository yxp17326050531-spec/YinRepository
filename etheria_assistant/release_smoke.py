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
                if not window.overview_header.property('decorated') or any(
                        corner.isNull() for corner in window.overview_header.corners):
                    raise RuntimeError('Gold overview header artwork missing')
                if any(button.icon().isNull() for button in window.nav.buttons()):
                    raise RuntimeError('Sidebar icon missing')
                window.theme_picker.setCurrentIndex(window.theme_picker.findData('classic'))
                if window.overview_header.property('decorated') or archive.settings().get('interface_theme') != 'classic':
                    raise RuntimeError('Interface theme switch failed')
                result={'ok':True,'version':VERSION,'check':'Qt startup, isolated archive, mappings, artwork and themes'}
            finally:
                if window:window.close();app.processEvents()
                if archive:
                    for handler in archive.logger.handlers[:]:handler.close();archive.logger.removeHandler(handler)
        from exe_updater import install_root, record_update_cleanup
        record_update_cleanup(report, install_root(), VERSION)
    except Exception:result={'ok':False,'error':traceback.format_exc()}
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1
