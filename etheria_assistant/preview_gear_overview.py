"""Render synthetic native UI preview; never opens the user's archive."""
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from storage import Archive
from qt_app import MainWindow


def attribute(tag,value):
    scale=100 if tag in (4,8,12,16) else 10
    return (round(value*scale)<<12)|(tag<<4)


def demo_inventory():
    result=[]
    def add(matrix,points,subs):
        result.append({'uid':90000+len(result),'level':15,'config_id':99999,'matrix':{'id':matrix,'points':points},
                       'attributes_raw':[attribute(8,330)]+[attribute(t,v) for t,v in subs],'flag_raw':1})
    for i in range(7):
        add(4 if i%2==0 else 64,3,[(16,17.1+i*.3),(3,3+i*.3),(11,2.4),(25,4.2)])
        add(17,3,[(7,12+i*.6),(19,10+i*.3),(22,16+i*.6),(16,7.2+i*.3)])
        add(32,3,[(3,11+i*.6),(19,8+i*.3),(22,14+i*.6),(16,7.2+i*.3)])
        add(39,3,[(11,12+i*.6),(19,9+i*.3),(22,16+i*.6),(16,6.3+i*.3)])
        add(5,2,[(3,12+i*.3),(11,11+i*.3),(16,10.2+i*.3),(28,15+i*.6)])
        add(12,2,[(3,10+i*.3),(11,9+i*.3),(25,17+i*.6),(28,16+i*.6)])
    add(4,3,[(16,19.5),(3,3.2),(11,3.2),(25,4.2)])
    add(64,3,[(16,18.9),(3,3.2),(11,3.2),(25,4.2)])
    return {'gear':result,'capture_time':0}


def main():
    app=QApplication.instance() or QApplication([])
    font=Path('/tmp/NotoSansCJKsc-Regular.otf')
    if font.is_file():
        fid=QFontDatabase.addApplicationFont(str(font))
        if fid>=0:app.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    out=Path(__file__).parent/'previews';out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive=Archive(tmp);window=MainWindow(archive)
        try:
            window.timer.stop();window.bag_snapshot=demo_inventory();window.render_inventory();window.navigate(2)
            window.gear_score_sort.setChecked(True);window.gear_table.selectRow(0)
            window.bag_info.setText('合成库存预览 · 仅用于展示界面效果，不是用户背包数据')
            window.gear_overview.badge.setText('预览 · 演示数据');window.show();window.resize(1280,800)
            for _ in range(5):app.processEvents()
            window.grab().save(str(out/'gear_overview.png'))
            window.gear_overview.grab().save(str(out/'gear_overview_detail.png'))
            window.gear_overview.toggle.setChecked(False)
            for _ in range(3):app.processEvents()
            window.grab().save(str(out/'gear_overview_collapsed.png'))
            print('Rendered native Qt preview:',out)
        finally:
            window.close();app.processEvents()
            for h in archive.logger.handlers[:]:h.close();archive.logger.removeHandler(h)


if __name__=='__main__':main()
