"""Native Qt compact score card and a painted radar; no plotting/browser dependency."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF,QFont,QFontMetrics
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,
                              QPushButton,QSpinBox,QSizePolicy)
from gear_overview import overview_metrics,top_count


def text(value,style=''):
    w=QLabel(value);w.setTextFormat(Qt.TextFormat.PlainText)
    w.setStyleSheet('background:transparent;border:0;'+style);return w


class GearRadar(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.axes=[];self.targets=[];self.setMinimumSize(300,158)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding);self.setMouseTracking(True)
        self.setAccessibleName('六维源器用途雷达图')
    def set_axes(self,axes):
        self.axes=axes;self.setAccessibleDescription('\n'.join(self.axis_tip(a) for a in axes));self.update()
    @staticmethod
    def axis_tip(a):
        percent=f"{a['percent']:.1f}" if a['percent'] is not None else '无参考值'
        return f"{a['name']}：前{a['count']}件合计 {a['raw']:.2f} / 参考 {a['reference']:.2f}；刻度 {percent}。各轴可重复使用源器，不能相加当总分。"
    def mouseMoveEvent(self,event):
        if self.targets:
            i=min(range(len(self.targets)),key=lambda j:(self.targets[j]-event.position()).manhattanLength())
            self.setToolTip(self.axis_tip(self.axes[i]))
        super().mouseMoveEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height();center=QPointF(w/2,h/2)
        radius=max(10,min((w-150)/2,(h-46)/2));angles=[-math.pi/2+i*math.pi/3 for i in range(6)]
        def point(i,f=1):return QPointF(center.x()+math.cos(angles[i])*radius*f,center.y()+math.sin(angles[i])*radius*f)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for level in range(1,6):
            p.setPen(QPen(QColor('#45384f' if level==5 else '#302a3b'),1))
            p.drawPolygon(QPolygonF([point(i,level/5) for i in range(6)]))
        p.setPen(QPen(QColor('#393144'),1))
        for i in range(6):p.drawLine(center,point(i))
        if len(self.axes)==6:
            polygon=QPolygonF([point(i,a['draw_percent']/100) for i,a in enumerate(self.axes)])
            p.setBrush(QColor(80,211,212,52));p.setPen(QPen(QColor('#59d8dc'),2));p.drawPolygon(polygon)
            for v in polygon:
                p.setBrush(QColor('#94f4eb'));p.setPen(QPen(QColor('#234c54'),1));p.drawEllipse(v,3,3)
        font=QFont(self.font());font.setPixelSize(12);p.setFont(font);fm=QFontMetrics(font)
        self.targets=[]
        for i,a in enumerate(self.axes):
            anchor=point(i,1.24);self.targets.append(anchor)
            value=f"{a['percent']:.0f}" if a['percent'] is not None else '—'
            label=a['name']+'  '+value
            width=fm.horizontalAdvance(label)+8;height=fm.height()+4
            rect=QRectF(anchor.x()-width/2,anchor.y()-height/2,width,height)
            rect.moveLeft(max(0,min(rect.left(),w-width)));rect.moveTop(max(0,min(rect.top(),h-height)))
            p.setPen(QColor('#ffcf65' if i==0 else '#c4bdd3'));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,label)
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
        self.badge=text('预览', 'color:#70dcce;font-size:11px;');header.addWidget(self.badge)
        header.addStretch();header.addWidget(text('各用途前', 'color:#9c93ac;font-size:12px;'))
        self.n=QSpinBox();self.n.setRange(1,20);self.n.setValue(top_count(n));self.n.setFixedWidth(66);self.n.setStyleSheet('padding:2px;')
        header.addWidget(self.n);header.addWidget(text('件', 'color:#9c93ac;font-size:12px;'))
        self.body=QWidget();self.body.setStyleSheet('background:transparent;');outer.addWidget(self.body)
        row=QHBoxLayout(self.body);row.setContentsMargins(0,0,0,0);row.setSpacing(12)
        left=QVBoxLayout();left.setSpacing(3);left.addStretch();row.addLayout(left,3)
        left.addWidget(text('源器总评分', 'color:#b6a4ca;font-size:13px;'))
        self.total=text('—','color:#ffd170;font-size:40px;font-weight:800;');self.total.setAccessibleName('全库存源器总评分');left.addWidget(self.total)
        self.counts=text('等待导入源器库存','color:#d0c7dd;font-size:12px;');left.addWidget(self.counts)
        self.note=text('全库存 · 每件只取最高用途分','color:#9d92ac;font-size:11px;');left.addWidget(self.note)
        self.compact=text('','color:#9d92ac;font-size:11px;');left.addWidget(self.compact);left.addStretch()
        self.radar=GearRadar();row.addWidget(self.radar,4)
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
        self.footer=text('各轴可重复使用源器 · 固定参考刻度，非全服百分位','color:#887f98;font-size:10px;');self.footer.setWordWrap(True);outer.addWidget(self.footer)
        self.toggle.toggled.connect(self.change_expanded);self.n.valueChanged.connect(self.change_n)
        self.change_expanded(expanded,notify=False)
    def change_expanded(self,expanded,notify=True):
        self.body.setVisible(expanded);self.footer.setVisible(expanded);self.n.setEnabled(expanded)
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
        self.radar.set_axes(m['axes'])
        for key,count in m['speed_bins'].items():self.bin_labels[key].setText(str(count))
        self.speed_note.setToolTip(f"按解码速度四舍五入分档；无已知速度副属性 {m['unknown_speed']} 件。强化次数不参与。")
        self.footer.setText(f"各轴前{m['top_n']}件 / 固定参考值 · 同件可跨轴，不能相加 · 非全服百分位")
        self.change_expanded(self.toggle.isChecked(),notify=False)
