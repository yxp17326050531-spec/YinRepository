"""Native Qt compact score card and a painted radar; no plotting/browser dependency."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF,QFont,QFontMetrics
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,
                              QPushButton,QSpinBox,QSizePolicy,QComboBox)
from gear_overview import overview_metrics,top_count


def text(value,style=''):
    w=QLabel(value);w.setTextFormat(Qt.TextFormat.PlainText)
    w.setStyleSheet('background:transparent;border:0;'+style);return w


class GearRadar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.axes = []
        self.targets = []
        self.count_mode = True
        self.scale = 100
        self.setMinimumSize(312, 210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName('六维源器用途雷达图')

    def set_axes(self, axes, count_mode=True):
        self.axes = axes
        self.count_mode = count_mode
        self.targets = []
        self.scale = 100
        if count_mode:
            peak = max((a['eligible_count'] for a in axes), default=0)
            step = max(1, 10 ** (len(str(max(1, peak))) - 1) // 2)
            self.scale = max(1, math.ceil(peak / step) * step)
        self.setAccessibleDescription('\n'.join(self.axis_tip(a) for a in axes))
        self.update()

    def axis_tip(self, a):
        if self.count_mode:
            return f"{a['name']}：全库存有 {a['eligible_count']} 件达到该用途门槛。同件在同一轴只计一次。"
        value = f"{a['percent']:.1f}%" if a['percent'] is not None else '无参考值'
        return f"{a['name']}：前 {a['count']} 件合计 {a['raw']:.2f} / 参考 {a['reference']:.2f}，参考达成 {value}。"

    def mouseMoveEvent(self, event):
        if self.targets:
            nearest = min(range(len(self.targets)), key=lambda i: (self.targets[i] - event.position()).manhattanLength())
            self.setToolTip(self.axis_tip(self.axes[nearest]))
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        if len(self.axes) != 6:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        center = QPointF(w / 2, h / 2)
        radius = min((w - 172) / 1.74, (h - 60) / 2)
        def point(i, fraction=1):
            angle = math.pi * (i / 3 - .5)
            return center + QPointF(math.cos(angle), math.sin(angle)) * (radius * fraction)

        p.setBrush(QColor('#191822'))
        p.setPen(QPen(QColor('#423c51'), 1))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 9, 9)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for level in (.25, .5, .75, 1):
            p.setPen(QPen(QColor('#615871' if level == 1 else '#3d374b'), 1))
            p.drawPolygon(QPolygonF([point(i, level) for i in range(6)]))
        p.setPen(QPen(QColor('#494254'), 1))
        for i in range(6):
            p.drawLine(center, point(i))

        values = [a['eligible_count'] if self.count_mode else a['percent'] for a in self.axes]
        known = [v for v in values if v is not None]
        low, high = (min(known), max(known)) if known else (0, 0)
        vertices = [point(i, min(v / self.scale, 1)) if v is not None else None for i, v in enumerate(values)]
        p.setPen(QPen(QColor('#53e2d5'), 2.6))
        if all(v is not None for v in vertices):
            p.setBrush(QColor(33, 210, 194, 78))
            p.drawPolygon(QPolygonF(vertices))
        else:
            for i, v in enumerate(vertices):
                prev = vertices[i - 1]
                if v is not None and prev is not None:
                    p.drawLine(prev, v)

        def label(rect, value, size, bold, color, align=Qt.AlignmentFlag.AlignCenter):
            font = QFont(self.font())
            font.setPixelSize(size)
            font.setBold(bold)
            p.setFont(font)
            p.setPen(QColor(color))
            p.drawText(rect, align, value)

        self.targets = []
        for i, (axis, v) in enumerate(zip(self.axes, values)):
            name = axis['name']
            color = '#e6f1f2'
            badge = ''
            if v is not None and high > low:
                if v == high:
                    color, badge = '#ffd478', ('最多' if self.count_mode else '最高')
                elif v == low:
                    color, badge = '#ffaca7', ('最少' if self.count_mode else '最低')
            vertex = vertices[i]
            if vertex is not None:
                p.setPen(QPen(QColor('#17242a'), 1.4))
                p.setBrush(QColor(color if badge else '#86fff0'))
                p.drawEllipse(vertex, 4.2, 4.2)
            value = '—' if v is None else (f'{v:,}件' if self.count_mode else f'{v:.0f}%')
            title = (badge + ' · ' if badge else '') + name
            edge = point(i)
            if i in (0, 3):
                y = edge.y() - 25 if i == 0 else edge.y() + 3
                name_font = QFont(self.font())
                name_font.setPixelSize(13)
                name_width = QFontMetrics(name_font).horizontalAdvance(title) + 7
                value_font = QFont(self.font())
                value_font.setPixelSize(19)
                value_font.setBold(True)
                value_width = QFontMetrics(value_font).horizontalAdvance(value) + 5
                x = center.x() - (name_width + value_width) / 2
                label(QRectF(x, y, name_width, 22), title, 13, False, '#d5ccdf')
                label(QRectF(x + name_width, y, value_width, 22), value, 19, True, color)
                self.targets.append(QPointF(center.x(), y + 11))
            else:
                right = i in (1, 2)
                x = edge.x() + 6 if right else 3
                width = w - x - 3 if right else edge.x() - x - 6
                align = (Qt.AlignmentFlag.AlignLeft if right else Qt.AlignmentFlag.AlignRight) | Qt.AlignmentFlag.AlignVCenter
                # Split the rank and axis labels at compact widths.
                if width < 112:
                    name_y = edge.y() - 23
                    label(QRectF(x, name_y, width, 15), badge, 10, True, color, align)
                    label(QRectF(x, name_y + 15, width, 17), name, 13, False, '#d5ccdf', align)
                    value_y = name_y + 31
                else:
                    label(QRectF(x, edge.y() - 17, width, 17), title, 13, False, '#d5ccdf', align)
                    value_y = edge.y()
                label(QRectF(x, value_y, width, 25), value, 19, True, color, align)
                self.targets.append(QPointF(x + width / 2, edge.y()))
        p.end()


class GearOverview(QFrame):
    preferencesChanged=Signal(bool,int)
    def __init__(self,expanded=True,n=5,parent=None):
        super().__init__(parent);self.setObjectName('gearOverview');self.metrics=None;self._scores={};self._rules=None
        self.setStyleSheet('QFrame#gearOverview {background:#1c1925;border:1px solid #3c334b;border-radius:10px;}')
        outer=QVBoxLayout(self);outer.setContentsMargins(14,7,14,8);outer.setSpacing(3)
        header=QHBoxLayout();outer.addLayout(header)
        self.toggle=QPushButton('练度概览');self.toggle.setCheckable(True);self.toggle.setChecked(expanded)
        self.toggle.setStyleSheet('text-align:left;border:0;background:transparent;color:#ded5ed;padding:3px;font-size:14px;font-weight:600;')
        self.toggle.setAccessibleName('展开或收起练度概览');header.addWidget(self.toggle)
        self.badge=text('初版', 'color:#70dcce;font-size:11px;');header.addWidget(self.badge)
        header.addStretch()
        self.mode = QComboBox()
        self.mode.addItems(['库存件数', '前 N 件质量'])
        self.mode.setAccessibleName('雷达图口径')
        header.addWidget(self.mode)
        self.n_caption = text('各用途前', 'color:#c6bcd2;font-size:12px;')
        header.addWidget(self.n_caption)
        self.n=QSpinBox();self.n.setRange(1,20);self.n.setValue(top_count(n));self.n.setFixedWidth(66);self.n.setStyleSheet('padding:2px;')
        header.addWidget(self.n)
        self.unit_caption = text('件', 'color:#c6bcd2;font-size:12px;')
        header.addWidget(self.unit_caption)
        self.body=QWidget();self.body.setStyleSheet('background:transparent;');outer.addWidget(self.body)
        row=QHBoxLayout(self.body);row.setContentsMargins(0,0,0,0);row.setSpacing(12)
        left=QVBoxLayout();left.setSpacing(3);left.addStretch();row.addLayout(left,3)
        left.addWidget(text('源器总评分', 'color:#b6a4ca;font-size:13px;'))
        self.total=text('—','color:#ffd170;font-size:40px;font-weight:800;');self.total.setAccessibleName('全库存源器总评分');left.addWidget(self.total)
        self.counts=text('等待导入源器库存','color:#d0c7dd;font-size:12px;');left.addWidget(self.counts)
        self.note=text('全库存 · 每件只取最高用途分','color:#9d92ac;font-size:11px;');left.addWidget(self.note)
        self.compact=text('','color:#9d92ac;font-size:11px;');left.addWidget(self.compact);left.addStretch()
        self.radar=GearRadar();row.addWidget(self.radar,6)
        right=QVBoxLayout();right.setSpacing(5);right.addWidget(text('速度储备', 'color:#d4c6e4;font-size:13px;font-weight:600;'))
        grid=QGridLayout();grid.setHorizontalSpacing(20);grid.setVerticalSpacing(6);right.addLayout(grid)
        self.bin_labels={}
        for i,key in enumerate(('低于14','14–16','17','18','19','20+')):
            box=QVBoxLayout();box.setSpacing(0)
            box.addWidget(text(key+'速','color:#9e93ae;font-size:11px;'))
            count=text('0','color:'+('#ffd170' if key in ('19','20+') else '#e1d8eb')+';font-size:20px;font-weight:700;')
            box.addWidget(count);grid.addLayout(box,i//3,i%3);self.bin_labels[key]=count
        self.speed_note=text('按游戏四舍五入值统计','color:#9d92ac;font-size:10px;');right.addWidget(self.speed_note);right.addStretch()
        row.addLayout(right,3)
        self.footer=text('', 'color:#bdb3cb;font-size:12px;');self.footer.setWordWrap(True);outer.addWidget(self.footer)
        self.toggle.toggled.connect(self.change_expanded);self.n.valueChanged.connect(self.change_n)
        self.mode.currentIndexChanged.connect(self.refresh_radar)
        self.refresh_radar()
        self.change_expanded(expanded,notify=False)
    def change_expanded(self,expanded,notify=True):
        self.mode.setVisible(expanded)
        self.body.setVisible(expanded);self.footer.setVisible(expanded);self.n.setEnabled(expanded)
        for widget in (self.n_caption, self.n, self.unit_caption):
            widget.setVisible(expanded and self.mode.currentIndex() == 1)
        self.toggle.setText(('▾ ' if expanded else '▸ ')+'练度概览'+('' if expanded or self.metrics is None else f"   ·   总分 {self.metrics['total']:,.1f}"))
        self.updateGeometry()
        if notify:self.preferencesChanged.emit(expanded,self.n.value())
    def change_n(self):
        if self._rules is not None:self.set_scores(self._scores,self._rules)
        self.preferencesChanged.emit(self.toggle.isChecked(),self.n.value())
    def set_scores(self,scores,rules):
        self._scores=scores;self._rules=rules;self.metrics=overview_metrics(scores,rules,self.n.value());m=self.metrics
        self.total.setText(f"{m['total']:,.1f}" if m['count'] else '—')
        self.total.setToolTip(f"全库存总分 {m['total']:.2f}；与列表用途或搜索筛选无关。")
        self.counts.setText(f"已评分 {m['rated']} / {m['count']} 件" if m['count'] else '等待导入源器库存')
        self.compact.setText(f"词条不完整 {m['incomplete']} 件 · 规则 {rules['revision']}")
        self.refresh_radar()
        for key,count in m['speed_bins'].items():self.bin_labels[key].setText(str(count))
        self.speed_note.setToolTip(f"按解码速度四舍五入分档；无已知速度副属性 {m['unknown_speed']} 件。强化次数不参与。")
        self.change_expanded(self.toggle.isChecked(),notify=False)

    def refresh_radar(self):
        counts = self.mode.currentIndex() == 0
        for widget in (self.n_caption, self.n, self.unit_caption):
            widget.setVisible(self.toggle.isChecked() and not counts)
        if self.metrics is None:
            return
        self.radar.set_axes(self.metrics['axes'], counts)
        if counts:
            self.footer.setText(f'达标件数 / 全库存 {self.metrics["count"]:,} 件    ·    外圈 {self.radar.scale:,} 件    ·    同件可计入多个用途')
        else:
            self.footer.setText(f'各用途前 {self.n.value()} 件的评分合计 ÷ 固定参考分    ·    外圈 100%    ·    同件可跨用途')
