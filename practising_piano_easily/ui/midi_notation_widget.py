"""Synchronized two-system or full-score notation, with adjustable size and line density."""

from bisect import bisect_right
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractScrollArea

from .score_widget import note_y
from .i18n import tr


SHARP_NATURALS = (0, 0, 2, 2, 4, 5, 5, 7, 7, 9, 9, 11)


def written_pitch(pitch):
    """Keep ledger lines readable; return written pitch and the explicit octave displacement."""
    written = pitch
    while written > 96:
        written -= 12
    while written < 24:
        written += 12
    return written, (pitch - written) // 12


def rhythm_glyph(beats):
    # shortcut: expressive MIDI durations use the nearest basic glyph; playback always uses the original times.
    values = (4, 3, 2, 1.5, 1, .75, .5, .375, .25, .1875, .125, .0625)
    value = min(values, key=lambda candidate: abs(math.log(max(.001, beats) / candidate)))
    dotted = value in (3, 1.5, .75, .375, .1875)
    base = value / 1.5 if dotted else value
    flags = max(0, round(-math.log2(base))) if base < 1 else 0
    return base, dotted, flags


class MidiNotationWidget(QAbstractScrollArea):
    HEADER = 100
    SYSTEM_HEIGHT = 290

    def __init__(self, *, full_score=False):
        super().__init__()
        self.full_score = full_score
        self.zoom_percent = 100
        self.bars_per_system = 0
        self.score = self.timeline = None
        self.position = 0.0
        self.current_measure = 0
        self.chord_text = ""
        self.measure_widths = ()
        self.systems = ()
        self.measure_systems = ()
        self.measure_bounds = ()
        self.first_system = 0
        self.scale = 1.0
        self.content_width = self.content_height = 0
        self.segments = ()
        # Keep the viewport size stable when zooming or following long scores.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.setMinimumHeight(280)

    def set_layout_options(self, zoom_percent, bars_per_system):
        if (not isinstance(zoom_percent, int) or not 50 <= zoom_percent <= 200
                or not isinstance(bars_per_system, int) or not 0 <= bars_per_system <= 8):
            raise ValueError("Choose a zoom from 50 to 200 and zero (automatic) to eight bars per line")
        self.zoom_percent, self.bars_per_system = zoom_percent, bars_per_system
        self._layout_systems()
        self.set_position(self.position, self.chord_text, force_follow=True)

    def set_score(self, score):
        self.score, self.timeline = score, score.timeline
        measures = self.timeline.measures
        segments = [[] for _ in measures]
        count = 0
        for note in score.notes:
            start, end = self.timeline.beat_at(note.start), self.timeline.beat_at(note.end)
            first = self.timeline.measure_index(note.start)
            last = self.timeline.measure_index(max(note.start, note.end - 1e-7))
            for index in range(first, last + 1):
                measure = measures[index]
                segments[index].append((note, max(start, measure.start_beat), min(end, measure.end_beat),
                                        start < measure.start_beat - 1e-6, end > measure.end_beat + 1e-6))
                count += 1
                if count > 200_000:
                    raise ValueError("Too many notation segments for the synchronized score")
        self.segments = tuple(tuple(sorted(items, key=lambda item: (item[1], item[0].pitch))) for items in segments)
        widths = []
        for measure, items in zip(measures, segments):
            onsets = len({round(item[1], 5) for item in items})
            width = max(340, min(1600, onsets * 54 + 80), (measure.end_beat - measure.start_beat) * 65)
            widths.append(width)
        self.measure_widths = tuple(widths)
        self._layout_systems()
        self.set_position(0, force_follow=True)

    def _layout_systems(self):
        base = 1.0 if self.full_score else min(1.0, max(1, self.viewport().height()) / (2 * self.SYSTEM_HEIGHT))
        self.scale = base * self.zoom_percent / 100
        available = max(100, self.viewport().width() / self.scale - self.HEADER - 25)
        systems, bounds, measure_systems = [], [], []
        first = 0
        while first < len(self.measure_widths):
            last, width = first + 1, self.measure_widths[first]
            while (last < min(first + (self.bars_per_system or 4), len(self.measure_widths))
                   and (self.bars_per_system or width + self.measure_widths[last] <= available)):
                width += self.measure_widths[last]
                last += 1
            line_width = max(available, width) if self.bars_per_system else available
            left = self.HEADER
            for natural_width in self.measure_widths[first:last]:
                right = left + line_width * natural_width / width
                bounds.append((left, right))
                measure_systems.append(len(systems))
                left = right
            systems.append((first, last))
            first = last
        self.systems, self.measure_bounds = tuple(systems), tuple(bounds)
        self.measure_systems = tuple(measure_systems)
        self.content_width = max((right for _, right in bounds), default=0) * self.scale + 25 * self.scale
        rows = len(systems) if self.full_score else min(2, len(systems))
        self.content_height = rows * self.SYSTEM_HEIGHT * self.scale
        self.horizontalScrollBar().setRange(0, max(0, math.ceil(self.content_width - self.viewport().width())))
        self.verticalScrollBar().setRange(0, max(0, math.ceil(self.content_height - self.viewport().height())))
        self.horizontalScrollBar().setPageStep(self.viewport().width())
        self.verticalScrollBar().setPageStep(self.viewport().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_systems()
        if self.score:
            self.set_position(self.position, self.chord_text, force_follow=True)

    def beat_x(self, beat, index=None):
        index = max(0, min(len(self.segments) - 1, bisect_right(self.timeline.measure_starts, beat) - 1)) if index is None else index
        measure = self.timeline.measures[index]
        fraction = (beat - measure.start_beat) / (measure.end_beat - measure.start_beat)
        left, right = self.measure_bounds[index]
        padding = 64 if self._meter_change(index) else 32
        return left + padding + fraction * max(1, right - left - padding - 32)

    def _meter_change(self, index):
        if index == self.systems[self.measure_systems[index]][0]:
            return False
        previous, measure = self.timeline.measures[index - 1:index + 1]
        return (previous.numerator, previous.denominator) != (measure.numerator, measure.denominator)

    def set_position(self, seconds, chord_text="", *, force_follow=False):
        previous_system = self.measure_systems[min(self.current_measure, len(self.measure_systems) - 1)] if self.measure_systems else -1
        previous_first = self.first_system
        time_changed = seconds != self.position
        self.position, self.chord_text = seconds, chord_text
        if self.timeline:
            self.current_measure = self.timeline.measure_index(seconds)
            # Keep the whole line still; only advance the two-line window at a system boundary.
            system = self.measure_systems[self.current_measure]
            self.first_system = 0 if self.full_score else min(system, max(0, len(self.systems) - 2))
            row = system if self.full_score else system - self.first_system
            top = row * self.SYSTEM_HEIGHT * self.scale
            scroll = self.verticalScrollBar().value()
            outside = top + 30 * self.scale < scroll or top + 274 * self.scale > scroll + self.viewport().height()
            if force_follow or previous_system != system or (self.full_score and time_changed and outside):
                if self.full_score or previous_first != self.first_system:
                    self.verticalScrollBar().setValue(round(top if self.full_score else 0))
                else:
                    self.verticalScrollBar().setValue(round(max(0, top + self.SYSTEM_HEIGHT * self.scale - self.viewport().height())))
            beat = min(max(0, self.timeline.beat_at(seconds)), max(0, self.timeline.end_beat - 1e-8))
            x = self.beat_x(beat, self.current_measure) * self.scale
            bar = self.horizontalScrollBar()
            if force_follow or previous_system != system:
                bar.setValue(0)
            if x < bar.value() or x > bar.value() + self.viewport().width() - 20:
                bar.setValue(round(max(0, x - self.viewport().width() * .3)))
        self.viewport().update()

    def measure_rect(self, index):
        left, right = self.measure_bounds[index]
        top = (self.measure_systems[index] - self.first_system) * self.SYSTEM_HEIGHT
        return QRectF(left * self.scale - self.horizontalScrollBar().value(),
                      (top + 30) * self.scale - self.verticalScrollBar().value(),
                      (right - left) * self.scale, 244 * self.scale)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.viewport().rect(), Qt.GlobalColor.white)
        if self.score is None:
            return
        scroll_y = self.verticalScrollBar().value()
        painter.translate(-self.horizontalScrollBar().value(), -scroll_y)
        painter.scale(self.scale, self.scale)
        first = int(scroll_y / (self.SYSTEM_HEIGHT * self.scale)) if self.full_score else self.first_system
        last = min(len(self.systems), math.ceil((scroll_y + self.viewport().height()) / (self.SYSTEM_HEIGHT * self.scale))) if self.full_score else min(len(self.systems), first + 2)
        for system in range(first, last):
            painter.save()
            painter.translate(0, (system - self.first_system) * self.SYSTEM_HEIGHT)
            painter.setClipRect(QRectF(0, 0, self.content_width / self.scale, self.SYSTEM_HEIGHT))
            self._system(painter, *self.systems[system])
            painter.restore()

    @staticmethod
    def _hand(note):
        return note.voice if note.voice in {"right", "left"} else "right" if note.pitch >= 60 else "left"

    def _system(self, painter, first, last):
        for index in range(first, last):
            left, right = self.measure_bounds[index]
            active = index == self.current_measure
            if active:
                painter.fillRect(QRectF(left, 30, right - left, 244), QColor("#fef3c7"))
            painter.setPen(QPen(QColor("#94a3b8"), 1))
            for top in (94, 194):
                for line in range(5):
                    painter.drawLine(QPointF(left, top + line * 10), QPointF(right, top + line * 10))
            painter.drawLine(QPointF(right, 94), QPointF(right, 234))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#1d4ed8" if active else "#64748b"))
            painter.drawText(QPointF(left + 8, 23), f"{tr('Bar')} {index + 1}")
            if active:
                painter.drawText(QRectF(left + 110, 3, max(0, right - left - 120), 25), Qt.AlignmentFlag.AlignLeft, self.chord_text)
            measure = self.timeline.measures[index]
            painter.setPen(QPen(QColor("#cbd5e1"), 1, Qt.PenStyle.DotLine))
            for beat in range(math.ceil(measure.start_beat), math.ceil(measure.end_beat)):
                x = self.beat_x(beat, index)
                painter.drawLine(QPointF(x, 40), QPointF(x, 268))
            if self._meter_change(index):
                self._meter(painter, left + 4, measure)
            accidentals = {}
            for note, start, end, incoming, outgoing in self.segments[index]:
                hand = self._hand(note)
                written, octave = written_pitch(note.pitch)
                natural = written - written % 12 + SHARP_NATURALS[written % 12]
                key = (hand, natural)
                sharp = written != natural
                previous = accidentals.get(key, False)
                accidental = "♯" if sharp and not previous else "♮" if not sharp and previous else ""
                accidentals[key] = sharp
                x = self.beat_x(start, index)
                y = note_y(natural, hand) + (40 if hand == "right" else 0)
                color = "#2563eb" if note.start <= self.position + .001 < note.end else (
                    "#2563eb" if note.voice == "right" else "#0d9488" if note.voice == "left" else "#172033")
                self._note(painter, x, y, end - start, hand, accidental, octave, incoming, outgoing,
                           color)
            for hand, top in (("right", 94), ("left", 194)):
                if not any(self._hand(item[0]) == hand for item in self.segments[index]):
                    painter.fillRect(QRectF((left + right) / 2 - 7, top + 10, 14, 4), QColor("#172033"))
            if index == len(self.segments) - 1:
                painter.setPen(QPen(QColor("#172033"), 3))
                painter.drawLine(QPointF(right, 94), QPointF(right, 234))
                painter.setPen(QPen(QColor("#172033"), 1))
                painter.drawLine(QPointF(right - 6, 94), QPointF(right - 6, 234))
        if first <= self.current_measure < last:
            beat = min(max(0, self.timeline.beat_at(self.position)), max(0, self.timeline.end_beat - 1e-8))
            x = self.beat_x(beat, self.current_measure)
            painter.setPen(QPen(QColor("#f59e0b"), 2))
            painter.drawLine(QPointF(x, 30), QPointF(x, 274))
        self._header(painter, first)

    def _header(self, painter, first):
        painter.fillRect(QRectF(0, 0, self.HEADER, self.SYSTEM_HEIGHT), Qt.GlobalColor.white)
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        for top in (94, 194):
            for line in range(5):
                painter.drawLine(QPointF(26, top + line * 10), QPointF(self.HEADER, top + line * 10))
        painter.drawLine(QPointF(26, 94), QPointF(26, 234))
        painter.setPen(QColor("#172033"))
        painter.setFont(QFont("Segoe UI Symbol", 40))
        painter.drawText(QRectF(10, 75, 48, 82), Qt.AlignmentFlag.AlignCenter, "𝄞")
        painter.drawText(QRectF(10, 175, 48, 82), Qt.AlignmentFlag.AlignCenter, "𝄢")
        self._meter(painter, 64, self.timeline.measures[first])
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(2, 2, 95, 25), Qt.AlignmentFlag.AlignCenter, f"MIDI · {first + 1}")

    @staticmethod
    def _meter(painter, x, measure):
        painter.setPen(QColor("#172033"))
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        for top in (94, 194):
            for offset, text in ((-3, measure.numerator), (17, measure.denominator)):
                painter.drawText(QRectF(x, top + offset, 28, 27), Qt.AlignmentFlag.AlignCenter, str(text))

    def _note(self, painter, x, y, beats, hand, accidental, octave, incoming, outgoing, color):
        top, bottom = (94, 134) if hand == "right" else (194, 234)
        color = QColor(color)
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        for ledger in range(bottom + 10, round(y) + 1, 10):
            painter.drawLine(QPointF(x - 10, ledger), QPointF(x + 10, ledger))
        for ledger in range(top - 10, round(y) - 1, -10):
            painter.drawLine(QPointF(x - 10, ledger), QPointF(x + 10, ledger))
        base, dotted, flags = rhythm_glyph(beats)
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(color if base < 2 else QColor("white"))
        painter.drawEllipse(QRectF(x - 6, y - 4, 12, 8))
        if base < 4:
            direction = -1 if y >= top + 20 else 1
            stem_x = x + (6 if direction == -1 else -6)
            stem_y = y + direction * 28
            painter.drawLine(QPointF(stem_x, y), QPointF(stem_x, stem_y))
            for flag in range(flags):
                path = QPainterPath(QPointF(stem_x, stem_y - direction * flag * 6))
                path.cubicTo(stem_x + 12, stem_y - direction * (6 + flag * 6),
                             stem_x + 13, stem_y - direction * (12 + flag * 6), stem_x + 5, stem_y - direction * (19 + flag * 6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
        if dotted:
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x + 12, y - 3), 1.8, 1.8)
        painter.setPen(color)
        if accidental:
            painter.setFont(QFont("Segoe UI Symbol", 15))
            painter.drawText(QRectF(x - 24, y - 17, 17, 33), Qt.AlignmentFlag.AlignCenter, accidental)
        if octave:
            painter.setFont(QFont("Segoe UI", 7))
            text = "8va" if octave == 1 else "8vb" if octave == -1 else f"{octave:+} oct"
            painter.drawText(QRectF(x - 17, y - 32, 42, 16), Qt.AlignmentFlag.AlignCenter, text)
        for continued, offset in ((incoming, -22), (outgoing, 5)):
            if continued:
                path = QPainterPath(QPointF(x + offset, y + 10))
                path.quadTo(x + offset + 8, y + 18, x + offset + 16, y + 10)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
