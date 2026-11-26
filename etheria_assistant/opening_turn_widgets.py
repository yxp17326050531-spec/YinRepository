"""Opening-speed and estimated first-turn tracks for the battle overview."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from artwork import image_label, suspected_hero_name
from opening_turn import first_arrival, opening_units


class OpeningTurnTrack(QWidget):
    TILE_WIDTH = 60

    def __init__(self):
        super().__init__()
        self.setObjectName('openingTurnTrack')
        self.setFixedHeight(51)
        self.markers = []
        self.coordinates = []

    def add_marker(self, row, position, side, value, tooltip, override):
        tile = QWidget(self)
        tile.setObjectName('openingMarker')
        tile.setFixedSize(self.TILE_WIDTH, self.height())
        tile.setToolTip(tooltip)
        stack = QVBoxLayout(tile)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(1)
        ring = QFrame()
        ring.setObjectName('openingPortraitRing')
        ring.setProperty('side', side)
        ring.setFixedSize(30, 30)
        inside = QHBoxLayout(ring)
        inside.setContentsMargins(0, 0, 0, 0)
        name = row.unit['hero_name']
        avatar = image_label('heroes', suspected_hero_name(row.unit['hero_id'], name) or name, 26, override)
        source = avatar.pixmap()
        if not source.isNull():
            rounded = QPixmap(52, 52)
            rounded.setDevicePixelRatio(2)
            rounded.fill(Qt.GlobalColor.transparent)
            with QPainter(rounded) as painter:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                circle = QPainterPath()
                circle.addEllipse(0, 0, 26, 26)
                painter.setClipPath(circle)
                painter.drawPixmap(0, 0, source)
            avatar.setPixmap(rounded)
        avatar.setToolTip(tooltip)
        inside.addWidget(avatar)
        stack.addWidget(ring, alignment=Qt.AlignmentFlag.AlignHCenter)
        metric = QLabel(value)
        metric.setObjectName('openingMetric')
        metric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metric.setAccessibleName(tooltip)
        stack.addWidget(metric)
        self.markers.append((tile, position))
        tile.show()

    def clear(self):
        for tile, _ in self.markers:
            tile.hide()
            tile.deleteLater()
        self.markers.clear()

    def place_markers(self):
        margin = self.TILE_WIDTH // 2
        span = max(0, self.width() - 2 * margin)
        count = len(self.markers)
        targets = [margin + round(span * (position if position is not None else i / max(1, count - 1)))
                   for i, (_, position) in enumerate(self.markers)]
        centers = [max(target, margin + i * self.TILE_WIDTH) for i, target in enumerate(targets)]
        for i in range(1, count):
            centers[i] = max(centers[i], centers[i - 1] + self.TILE_WIDTH)
        for i in reversed(range(count)):
            right = centers[i + 1] - self.TILE_WIDTH if i + 1 < count else self.width() - margin
            centers[i] = min(centers[i], right)
        self.coordinates = []
        for (tile, position), target, center in zip(self.markers, targets, centers):
            tile.move(center - margin, 0)
            if position is not None:
                self.coordinates.append((target, center))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place_markers()

    def paintEvent(self, event):
        super().paintEvent(event)
        margin = self.TILE_WIDTH // 2
        if not self.markers:
            return
        rail, ticks = ('#89734f', '#c4aa80') if self.property('goldTheme') else ('#5a4c68', '#a79ab5')
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(rail), 2))
            painter.drawLine(margin, 15, self.width() - margin, 15)
            painter.setPen(QPen(QColor(ticks), 1))
            for target, center in self.coordinates:
                painter.drawLine(target, 3, target, 10)
                if target != center:
                    painter.drawLine(target, 10, center, 15)


class OpeningTurnStrip(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('openingTurnStrip')
        self.rows = []
        self.own_team = None
        self.portraits = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 3, 9, 3)
        layout.setSpacing(10)
        controls = QVBoxLayout()
        controls.setSpacing(1)
        self.title = QLabel('面板速度')
        self.title.setObjectName('openingTurnTitle')
        controls.addWidget(self.title)
        self.forecast = QPushButton('首动推演')
        self.forecast.setObjectName('openingMode')
        self.forecast.setCheckable(True)
        self.forecast.setToolTip('查看第一人预计到达 100% 时的行动进度。')
        self.forecast.toggled.connect(self.render_track)
        controls.addWidget(self.forecast)
        layout.addLayout(controls)
        self.track = OpeningTurnTrack()
        layout.addWidget(self.track, 1)
        self.hide()

    def set_roster(self, teams, own_team, portraits):
        self.rows = opening_units(teams)
        self.own_team = own_team
        self.portraits = portraits
        self.setVisible(bool(self.rows))
        self.render_track()

    def render_track(self):
        self.track.clear()
        forecast = self.forecast.isChecked()
        arrival = first_arrival(self.rows) if forecast else None
        leaders = [row for row in self.rows if arrival is not None and row.arrival == arrival]
        tied = len(leaders) > 1
        random_first = tied and len({row.speed for row in leaders}) == 1
        title = '面板速度'
        if forecast:
            title = ('随机先动' if random_first else '并列到线' if tied else
                     '到线待定' if arrival is None else '首次到线')
        self.title.setText(title)
        self.title.setToolTip('面板同速且开场行动进度相同时随机先动。'
                              '推演按速度连续累积，计入戍卫触发的梦引。冲坡效果待实战验证。')
        ordered = sorted(self.rows, key=lambda row: (row.speed is None, -(row.speed or 0)))
        if arrival is not None:
            ordered.sort(key=lambda row: row.advance + row.speed * arrival)
        self.track.setMinimumWidth(len(ordered) * self.track.TILE_WIDTH)
        for row in ordered:
            team_name = ('己方' if row.team == self.own_team else '敌方') if self.own_team else f'{row.team} 方'
            side = 'own' if row.team == (self.own_team or 'A') else 'enemy'
            speed = f'{float(row.speed):.2f}'.rstrip('0').rstrip('.') if row.speed is not None else '—'
            tooltip = f"{team_name} · {row.unit['hero_name']} · 面板速度 {speed}"
            if row.advance:
                tooltip += f'\n戍卫触发梦引 · 行动进度 +{row.advance} 个百分点'
            progress = row.advance + row.speed * arrival if arrival is not None else None
            if forecast:
                value = f'{int(progress * 10) / 10:g}%' if progress is not None else '—'
                if progress == 100:
                    tooltip += ('\n同速同刻到线 · 随机先动' if random_first else
                                '\n推演同刻到线 · 首动待确认' if tied else '\n预计先到 100%')
                elif progress is None:
                    tooltip += '\n缺少可用速度，到线待定'
                else:
                    tooltip += '\n第一人到线时预计进度 ' + value
            else:
                value = speed
            self.track.add_marker(row, float(progress / 100) if progress is not None else None,
                                  side, value, tooltip, self.portraits.get(str(row.unit['hero_id'])))
        self.track.place_markers()
