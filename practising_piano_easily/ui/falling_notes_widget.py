"""Falling blocks aligned with the shared piano geometry."""

from bisect import bisect_left

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from practising_piano_easily.trainers.chord_construction import midi_note_name
from .keyboard_widget import piano_key_rects, WHITE_PITCH_CLASSES


class FallingNotesWidget(QWidget):
    def __init__(self, keyboard):
        super().__init__()
        self.keyboard = keyboard
        self.session = None
        self.lookahead = 4.0
        self.setMinimumHeight(120)

    def block_rect(self, note):
        keys = piano_key_rects(self.keyboard.start_note, self.keyboard.end_note, self.width(), 130)
        lane = keys[note.pitch]
        scale = (self.height() - 12) / self.lookahead
        bottom = self.height() - 4 - (note.start - self.session.position) * scale
        height = max(7, (note.end - note.start) * scale)
        return QRectF(lane.x() + 2, bottom - height, max(3, lane.width() - 4), height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        keys = piano_key_rects(self.keyboard.start_note, self.keyboard.end_note, self.width(), 130)
        for pitch, key in keys.items():
            if pitch % 12 in WHITE_PITCH_CLASSES:
                painter.setPen(QPen(QColor("#24334b"), 1))
                painter.drawLine(QPointF(key.x(), 0), QPointF(key.x(), self.height()))
        if self.session is not None:
            session, score = self.session, self.session.score
            for note in score.visible_notes(session.position, self.lookahead):
                rect = self.block_rect(note)
                index = bisect_left(score.group_times, note.start)
                hit = (not session.preview and (index < session.follower.index or
                       (index == session.follower.index and note.pitch in session.follower.hits)))
                if hit:
                    color = "#22c55e"
                elif note.voice == "left":
                    color = "#14b8a6"
                elif note.voice.startswith("track:"):
                    color = ("#60a5fa", "#c084fc", "#2dd4bf", "#fb923c")[int(note.voice.split(":")[1]) % 4]
                else:
                    color = "#60a5fa"
                painter.setPen(QPen(QColor(color).lighter(120), 1))
                painter.setBrush(QColor(color))
                painter.drawRoundedRect(rect, 4, 4)
                if rect.width() > 18:
                    painter.setPen(QColor("#0b1324"))
                    painter.setFont(QFont("Segoe UI", max(6, min(10, int(rect.width() / 3.6))), QFont.Weight.Bold))
                    label_y = max(rect.top(), min(rect.bottom() - 22, self.height() - 27))
                    painter.drawText(QRectF(rect.x(), label_y, rect.width(), 22), Qt.AlignmentFlag.AlignCenter, midi_note_name(note.pitch))
        painter.setPen(QPen(QColor("#fbbf24"), 3))
        painter.drawLine(QPointF(0, self.height() - 3), QPointF(self.width(), self.height() - 3))
