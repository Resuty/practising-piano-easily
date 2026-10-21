"""Shared hand-practice choices with explicit limitations for imported MIDI."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSpinBox, QWidget

from practising_piano_easily.trainers.chord_construction import midi_note_name
from .localized_widgets import QComboBox, QLabel
from .i18n import language


class HandControls(QWidget):
    changed = Signal()

    def __init__(self, database, prefix):
        super().__init__()
        self.database, self.prefix = database, prefix
        self._score, self._track = None, -1
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Practice hands:"))
        self.hand = QComboBox()
        for label, value in (("Both hands", "both"), ("Right hand only", "right"), ("Left hand only", "left")):
            self.hand.addItem(label, value)
        self.hand.setCurrentIndex(max(0, self.hand.findData(database.get_setting(prefix + "_hand", "both"))))
        layout.addWidget(self.hand)
        layout.addWidget(QLabel("Split key:"))
        self.split = QSpinBox()
        self.split.setRange(21, 108)
        try:
            value = int(database.get_setting(prefix + "_split", "60"))
        except (ValueError, TypeError):
            value = 60
        self.split.setValue(value if 21 <= value <= 108 else 60)
        layout.addWidget(self.split)
        self.key_name = QLabel()
        layout.addWidget(self.key_name)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint, 1)
        self._saved = self.values()
        self.hand.currentIndexChanged.connect(self._changed)
        self.split.valueChanged.connect(self._changed)
        language.changed.connect(self._update_hint)
        self._update_hint()

    def values(self):
        return self.hand.currentData(), self.split.value()

    def apply(self, score, track=-1):
        self._score, self._track = score, track
        self._update_hint()
        return score.practice_part(*self.values(), track=track)

    def _update_hint(self):
        self.key_name.setText(midi_note_name(self.split.value()))
        explicit = self._score is not None and all(note.voice in {"right", "left"} for note in self._score.notes)
        self.split.setEnabled(not explicit and self._track == -1 and self.hand.currentData() != "both")
        self.hint.setText("Built-in hand assignments are used; the split key does not change them." if explicit else
                          "All selected notes are practiced. MIDI single-hand modes use an adjustable register split or a manually selected track." if self.hand.currentData() == "both" else
                          "MIDI has no reliable hand labels. The selected track is assigned to the chosen hand; please verify it." if self._track != -1 and self.hand.currentData() != "both" else
                          "MIDI hands are estimated by register: below the split key = left, at or above = right. Adjust the split or select a hand's track.")

    def metadata(self):
        explicit = all(note.voice in {"right", "left"} for note in self._score.notes) if self._score else False
        return {"practice_hand": self.hand.currentData(), "split_note": self.split.value(),
                "hand_assignment": "explicit" if explicit else "selected_track" if self._track != -1 else "register_estimate"}

    def question_suffix(self):
        if self.hand.currentData() == "both":
            return ""
        assignment = self.metadata()["hand_assignment"]
        return f":hand:{self.hand.currentData()}:" + (f"split:{self.split.value()}" if assignment == "register_estimate" else assignment)

    def _changed(self):
        self._update_hint()
        self.changed.emit()
        self.save_options()

    def save_options(self):
        values = self.values()
        if values == self._saved:
            return
        try:
            self.database.set_settings({self.prefix + "_hand": values[0], self.prefix + "_split": str(values[1])})
            self._saved = values
        except sqlite3.Error:
            self.hint.setText("Hand settings could not be saved. Current choices apply now; leaving or closing will retry.")

    def hideEvent(self, event):
        self.save_options()
        super().hideEvent(event)
