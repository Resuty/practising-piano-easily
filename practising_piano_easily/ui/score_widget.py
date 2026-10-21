"""Native grand staff for the built-in white-key exercises (quarter/half/whole notes)."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from practising_piano_easily.trainers.chord_construction import midi_note_name
from .i18n import language, tr


LETTERS = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}
STAFF_SPACE = 10


def note_y(note: int, hand: str) -> float:
    """Map written diatonic steps to staff space; C4 is the treble lower ledger line."""
    if note % 12 not in LETTERS:
        raise ValueError("The built-in score renderer currently supports natural notes only")
    position = (note // 12 - 1) * 7 + LETTERS[note % 12]
    bottom, base = (94, 30) if hand == "right" else (234, 18)
    return bottom - (position - base) * STAFF_SPACE / 2


class ScoreWidget(QWidget):
    page_changed = Signal()

    def __init__(self):
        super().__init__()
        self.lesson = None
        self.index = 0
        self.matched = False
        self.show_names = True
        self.page = 0
        self.bars_per_page = 4
        self.setMinimumSize(780, 260)
        language.changed.connect(self.update)

    def set_score(self, lesson, index=0, matched=False):
        self.lesson, self.index, self.matched = lesson, index, matched
        self.bars_per_page = 2 if any(step.beats < 1 for step in lesson.steps) else 4
        beat = sum(step.beats for step in lesson.steps[:min(index, len(lesson.steps) - 1)])
        self.set_page(int(beat // (4 * self.bars_per_page)))

    @property
    def page_count(self):
        bars = int(sum(step.beats for step in self.lesson.steps) / 4) if self.lesson else 0
        return max(1, (bars + self.bars_per_page - 1) // self.bars_per_page)

    def set_page(self, page):
        self.page = max(0, min(page, self.page_count - 1))
        self.page_changed.emit()
        self.update()

    def step_x(self, index):
        beat = sum(step.beats for step in self.lesson.steps[:index])
        width = (self.width() - 130) / self.bars_per_page
        return 110 + (beat // 4 - self.page * self.bars_per_page) * width + 24 + (beat % 4) * width / 4

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.scale(1, self.height() / 305)
        if self.lesson is None:
            return
        bars = int(sum(step.beats for step in self.lesson.steps) / 4)
        first_bar = self.page * self.bars_per_page
        visible_bars = min(self.bars_per_page, bars - first_bar)
        bar_width = (self.width() - 130) / self.bars_per_page
        current_beat = sum(step.beats for step in self.lesson.steps[:self.index])
        if self.index < len(self.lesson.steps) and first_bar * 4 <= current_beat < (first_bar + visible_bars) * 4:
            color = "#dcfce7" if self.matched else "#dbeafe"
            painter.fillRect(QRectF(self.step_x(self.index) - 15, 42, 31, 208), QColor(color))
        painter.setPen(QPen(QColor("#64748b"), 1))
        for top in (54, 194):
            for line in range(5):
                y = top + line * STAFF_SPACE
                painter.drawLine(QPointF(26, y), QPointF(self.width() - 20, y))
        painter.drawLine(QPointF(26, 54), QPointF(26, 234))
        for bar in range(1, visible_bars + 1):
            x = 110 + bar * bar_width
            painter.drawLine(QPointF(x, 54), QPointF(x, 234))
        painter.setPen(QColor("#172033"))
        painter.setFont(QFont("Segoe UI Symbol", 45))
        painter.drawText(QRectF(28, 34, 48, 87), Qt.AlignmentFlag.AlignCenter, "𝄞")
        painter.drawText(QRectF(28, 177, 48, 79), Qt.AlignmentFlag.AlignCenter, "𝄢")
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        for top in (54, 194):
            painter.drawText(QRectF(77, top - 3, 22, 28), Qt.AlignmentFlag.AlignCenter, "4")
            painter.drawText(QRectF(77, top + 17, 22, 28), Qt.AlignmentFlag.AlignCenter, "4")
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        for bar in range(visible_bars):
            painter.drawText(QPointF(110 + bar * bar_width + 12, 26), str(first_bar + bar + 1))
        beat = 0
        for index, step in enumerate(self.lesson.steps):
            visible = first_bar * 4 <= beat < (first_bar + visible_bars) * 4
            beat += step.beats
            if not visible:
                continue
            color = "#15803d" if index < self.index or (index == self.index and self.matched) else "#2563eb" if index == self.index else "#172033"
            for hand, notes in (("right", step.right), ("left", step.left)):
                self._draw_group(painter, self.step_x(index), hand, notes, step.beats, color)
        painter.setPen(QColor("#475569"))
        painter.drawText(QPointF(26, 293), tr("4/4 · Eighth = ½ · Quarter = 1 · Dotted quarter = 1½ · Half = 2 · Whole = 4 beats"))

    def _draw_group(self, painter, x, hand, notes, beats, color):
        top, bottom = (54, 94) if hand == "right" else (194, 234)
        painter.setPen(QPen(QColor(color), 1.4))
        if not notes:
            y = top + 10
            if beats in (2, 3, 4):
                painter.fillRect(QRectF(x - 6, y + (0 if beats == 4 else 7), 12, 3), QColor(color))
            elif beats == 0.5:
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(x - 3, y + 6), 3, 3)
                painter.drawLine(QPointF(x - 1, y + 8), QPointF(x + 5, y + 3))
                painter.drawLine(QPointF(x + 5, y + 3), QPointF(x - 2, y + 23))
            else:
                path = QPainterPath(QPointF(x + 2, y))
                path.lineTo(x - 3, y + 6)
                path.lineTo(x + 3, y + 13)
                path.lineTo(x - 2, y + 19)
                path.cubicTo(x - 9, y + 13, x - 8, y + 24, x - 1, y + 27)
                painter.drawPath(path)
            if beats in (1.5, 3):
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(x + 12, y + 8), 2, 2)
            return
        ys = [note_y(note, hand) for note in notes]
        for y in ys:
            painter.setPen(QPen(QColor("#64748b"), 1))
            line = bottom + STAFF_SPACE
            while line <= y:
                painter.drawLine(QPointF(x - 11, line), QPointF(x + 11, line))
                line += STAFF_SPACE
            line = top - STAFF_SPACE
            while line >= y:
                painter.drawLine(QPointF(x - 11, line), QPointF(x + 11, line))
                line -= STAFF_SPACE
            painter.setPen(QPen(QColor(color), 1.7))
            painter.setBrush(QColor(color) if beats in (0.5, 1, 1.5) else QColor("#ffffff"))
            painter.save()
            painter.translate(x, y)
            painter.rotate(-18)
            painter.drawEllipse(QRectF(-7, -4.5, 14, 9))
            painter.restore()
        if beats != 4:
            if sum(ys) / len(ys) >= top + 20:
                painter.drawLine(QPointF(x + 6, max(ys)), QPointF(x + 6, min(ys) - 30))
                stem_x, stem_y, direction = x + 6, min(ys) - 30, 1
            else:
                painter.drawLine(QPointF(x - 6, min(ys)), QPointF(x - 6, max(ys) + 30))
                stem_x, stem_y, direction = x - 6, max(ys) + 30, -1
            if beats == 0.5:
                flag = QPainterPath(QPointF(stem_x, stem_y))
                flag.cubicTo(stem_x + 14, stem_y + direction * 6,
                             stem_x + 15, stem_y + direction * 12, stem_x + 7, stem_y + direction * 21)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(flag)
        if beats in (1.5, 3):
            painter.setBrush(QColor(color))
            for y in ys:
                painter.drawEllipse(QPointF(x + 13, y - (5 if (bottom - y) % STAFF_SPACE == 0 else 0)), 2, 2)
        if self.show_names:
            painter.setFont(QFont("Segoe UI", 9))
            names = " ".join(midi_note_name(note) for note in notes)
            y = 154 if hand == "right" else 268
            painter.drawText(QRectF(x - 43, y - 12, 86, 26), Qt.AlignmentFlag.AlignCenter, names)
