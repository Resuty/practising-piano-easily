"""Clickable three-octave piano used for MIDI visualization and demo input."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget
from practising_piano_easily.trainers.chord_construction import midi_note_name


WHITE_PITCH_CLASSES = {0, 2, 4, 5, 7, 9, 11}


def piano_key_rects(start_note, end_note, width, height):
    """Shared lane/key geometry keeps falling blocks centered above the actual keys."""
    whites = [note for note in range(start_note, end_note) if note % 12 in WHITE_PITCH_CLASSES]
    white_width = width / len(whites)
    rects = {note: QRectF(index * white_width, 0, white_width + 0.5, height) for index, note in enumerate(whites)}
    white_index = {note: index for index, note in enumerate(whites)}
    for note in range(start_note, end_note):
        if note % 12 not in WHITE_PITCH_CLASSES:
            previous = max(candidate for candidate in whites if candidate < note)
            rects[note] = QRectF((white_index[previous] + 1) * white_width - white_width * 0.32,
                                0, white_width * 0.64, height * 0.62)
    return rects


class PianoKeyboard(QWidget):
    note_changed = Signal(int, bool)

    def __init__(self, start_note: int = 48, end_note: int = 84) -> None:
        super().__init__()
        self.start_note = start_note
        self.end_note = end_note
        self.pressed: frozenset[int] = frozenset()
        self.expected_pitch_classes: frozenset[int] = frozenset()
        self.expected_notes: frozenset[int] = frozenset()
        self.show_note_names = True
        self.label_all_notes = False
        self.reference_notes: frozenset[int] = frozenset()
        self.correct_notes: frozenset[int] = frozenset()
        self.incorrect_notes: frozenset[int] = frozenset()
        self._key_rects: dict[int, QRectF] = {}
        self.setMinimumHeight(150)

    def set_notes(self, pressed: frozenset[int], *, correct: frozenset[int] = frozenset(),
                  incorrect: frozenset[int] = frozenset()) -> None:
        self.pressed = pressed
        self.correct_notes = correct
        self.incorrect_notes = incorrect
        self.update()

    def set_expected(self, pitch_classes: frozenset[int]) -> None:
        self.expected_notes = frozenset()
        self.expected_pitch_classes = pitch_classes
        self.correct_notes = frozenset()
        self.incorrect_notes = frozenset()
        self.update()

    def set_expected_notes(self, notes: frozenset[int]) -> None:
        self.expected_notes = notes
        self.expected_pitch_classes = frozenset()
        self.update()

    def set_reference_notes(self, notes: frozenset[int]) -> None:
        self.reference_notes = notes
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        white_notes = [note for note in range(self.start_note, self.end_note) if note % 12 in WHITE_PITCH_CLASSES]
        white_width = self.width() / len(white_notes)
        self._key_rects = piano_key_rects(self.start_note, self.end_note, self.width(), self.height())
        for index, note in enumerate(white_notes):
            rect = self._key_rects[note]
            painter.fillRect(rect, self._color(note, False))
            painter.setPen(QPen(QColor("#475569"), 1))
            painter.drawRect(rect)
            self._reference_mark(painter, note, rect)
            if self.show_note_names:
                names = {0: "C", 2: "D", 4: "E", 5: "F", 7: "G", 9: "A", 11: "B"}
                name = names[note % 12]
                if note % 12 == 0:
                    name += str(note // 12 - 1)
                if self.label_all_notes:
                    name = midi_note_name(note)
                size = max(6, min(9, int(white_width / 3))) if self.label_all_notes else 9
                painter.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if note == 60 else QFont.Weight.Normal))
                painter.setPen(QColor("#9f1239" if note == 60 else "#334155"))
                painter.drawText(QRectF(rect.x(), self.height() - 27, white_width, 24), Qt.AlignmentFlag.AlignCenter, name)
        for note in range(self.start_note, self.end_note):
            if note % 12 in WHITE_PITCH_CLASSES:
                continue
            rect = self._key_rects[note]
            painter.fillRect(rect, self._color(note, True))
            painter.setPen(QPen(QColor("#0f172a"), 1))
            painter.drawRect(rect)
            self._reference_mark(painter, note, rect)
            if self.label_all_notes:
                painter.setFont(QFont("Segoe UI", max(6, min(9, int(rect.width() / 3.5)))))
                painter.setPen(QColor("#ffffff"))
                name = midi_note_name(note) if rect.width() >= 22 else f"{midi_note_name(note)[:-len(str(note // 12 - 1))]}\n{note // 12 - 1}"
                painter.drawText(QRectF(rect.x(), rect.height() - 30, rect.width(), 29),
                                 Qt.AlignmentFlag.AlignCenter, name)

    def _reference_mark(self, painter, note, rect):
        if note in self.reference_notes:
            painter.fillRect(QRectF(rect.x() + 3, rect.bottom() - 35, max(2, rect.width() - 6), 4), QColor("#a855f7"))

    def _color(self, note: int, black: bool) -> QColor:
        if note in self.incorrect_notes:
            return QColor("#ef4444")
        if note in self.correct_notes:
            return QColor("#22c55e")
        if note in self.pressed:
            return QColor("#3b82f6")
        if note in self.expected_notes or note % 12 in self.expected_pitch_classes:
            return QColor("#fde68a" if not black else "#a16207")
        return QColor("#111827" if black else "#f8fafc")

    def _note_at(self, position) -> int | None:
        black = [note for note in self._key_rects if note % 12 not in WHITE_PITCH_CLASSES]
        for note in black:
            if self._key_rects[note].contains(position):
                return note
        for note, rect in self._key_rects.items():
            if note % 12 in WHITE_PITCH_CLASSES and rect.contains(position):
                return note
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            note = self._note_at(event.position())
            if note is not None:
                self.note_changed.emit(note, note not in self.pressed)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        event.accept()
