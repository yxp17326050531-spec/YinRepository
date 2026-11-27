"""Small local portraits and matrix icons, matched by displayed name."""
import json
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QLabel

from core import load_mappings

ROOT=Path(__file__).resolve().parent/'assets'
SUSPECTED_HERO_NAMES = {32352: '奥萨尔'}


def suspected_hero_name(identifier, displayed_name):
    return SUSPECTED_HERO_NAMES.get(identifier) if displayed_name == f'角色 #{identifier}' else None


@lru_cache(maxsize=1)
def catalogue():
    try:return json.loads((ROOT/'catalogue.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


@lru_cache(maxsize=4)
def atlas(name):
    return QPixmap(str(ROOT/name)) if name in ('heroes.jpg','shells.jpg','matrices.png','darros.png') else QPixmap()


@lru_cache(maxsize=512)
def portrait(kind,name,size):
    item=catalogue().get(kind,{}).get(name)
    if not item:return QPixmap()
    image=atlas(item['atlas']).copy(*item['rect'])
    image=image.scaled(size*2,size*2,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    image.setDevicePixelRatio(2)
    return image


@lru_cache(maxsize=1)
def builtin_hero_names():
    return load_mappings().get('heroes', {})


def hero_portrait(name, size, override=None, *, hero_id=None):
    if override:
        builtin, png = override
        if png:
            image = QPixmap()
            if image.loadFromData(png, 'PNG'):
                image = image.scaled(size * 2, size * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                image.setDevicePixelRatio(2)
                return image
        if builtin:
            image = portrait('heroes', builtin, size)
            if not image.isNull():
                return image
    image = portrait('heroes', name, size)
    if image.isNull() and hero_id is not None:
        original = builtin_hero_names().get(str(hero_id))
        if original and original != name:
            return portrait('heroes', original, size)
    return image


def read_portrait_png(path):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 24_000_000:
        raise ValueError('无法读取图像，或图像尺寸过大')
    image = reader.read()
    if image.isNull():
        raise ValueError('无法读取图像：' + reader.errorString())
    side = min(image.width(), image.height())
    image = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
    image = image.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('无法保存头像图像')
    return bytes(buffer.data())


def image_label(kind,name,size,override=None,*,hero_id=None):
    label=QLabel();label.setObjectName('artIcon');label.setFixedSize(size,size)
    image=hero_portrait(name,size,override,hero_id=hero_id) if kind=='heroes' else portrait(kind,name,size)
    if image.isNull():
        label.setText('？' if kind=='heroes' else (name or '？')[:1])
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
