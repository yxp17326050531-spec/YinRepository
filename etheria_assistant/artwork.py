"""Small local portraits and matrix icons, matched by displayed name."""
import json
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

ROOT=Path(__file__).resolve().parent/'assets'


@lru_cache(maxsize=1)
def catalogue():
    try:return json.loads((ROOT/'catalogue.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


@lru_cache(maxsize=3)
def atlas(name):
    return QPixmap(str(ROOT/name)) if name in ('heroes.jpg','shells.jpg','matrices.png') else QPixmap()


@lru_cache(maxsize=512)
def portrait(kind,name,size):
    item=catalogue().get(kind,{}).get(name)
    if not item:return QPixmap()
    image=atlas(item['atlas']).copy(*item['rect'])
    image=image.scaled(size*2,size*2,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    image.setDevicePixelRatio(2)
    return image


def image_label(kind,name,size):
    label=QLabel();label.setObjectName('artIcon');label.setFixedSize(size,size)
    image=portrait(kind,name,size)
    if image.isNull():label.setText((name or '？')[:1]);label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    else:label.setPixmap(image)
    label.setAccessibleName(f'{kind}图片 {name}');label.setToolTip(name or '未识别')
    return label


def matrix_color(name):
    if name in ('浴血','浴血之躯','不屈','不屈之誓'):return '#ff6475'
    if name=='荆棘':return '#ffd34e'
    if name in ('奋进','时光','时光驾驭'):return '#6fb8ff'
    if name=='涌泉':return '#8de56d'
    if name in ('攻势','收割','狂怒','亵渎','乘势追击','洞悉穿刺','沸腾打击','暴烈利刃'):return '#ff8b86'
    if name in ('治愈','进化荫庇'):return '#8de56d'
    return '#9fbad2'
