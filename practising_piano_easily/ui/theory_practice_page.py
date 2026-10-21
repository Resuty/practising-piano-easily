"""Learn/Practice/Test UI for core keyboard and theory skills."""

from __future__ import annotations

import sqlite3
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QLabel, QMessageBox, QPushButton)

from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.trainers.chord_construction import midi_note_name
from practising_piano_easily.trainers.theory_practice import TheoryPracticeGenerator, check_answer, check_notes

from .keyboard_widget import PianoKeyboard


class TheoryPracticePage(QWidget):
    attempt_recorded = Signal()

    def __init__(self, controller: MidiController, database, session_id: int) -> None:
        super().__init__()
        self.controller, self.database, self.session_id = controller, database, session_id
        self.generator = TheoryPracticeGenerator()
        self.question = None
        self.active_notes: frozenset[int] = frozenset()
        self.sequence: list[int] = []
        self.scored = False
        self.last_correct = False
        self.completed = 0
        self.question_limit = 20
        self._active = False
        self.started = time.monotonic()
        layout = QVBoxLayout(self)
        title = QLabel("Theory Practice"); title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        controls = QHBoxLayout()
        self.training_mode = QComboBox(); self.training_mode.addItems(["Learn", "Practice", "Test"])
        self.kind = QComboBox(); self.kind.addItems([
            "Interval construction", "Scale", "Diatonic chord", "Roman: symbol → chord",
            "Roman: chord → function", "Inversion",
        ])
        controls.addWidget(QLabel("Mode:")); controls.addWidget(self.training_mode)
        controls.addWidget(QLabel("Exercise:")); controls.addWidget(self.kind, 1); layout.addLayout(controls)
        self.prompt = QLabel(); self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setStyleSheet("font-size: 34px; font-weight: 800; padding: 16px"); layout.addWidget(self.prompt)
        self.expected = QLabel(); self.expected.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.expected)
        self.played = QLabel("—"); self.played.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.played)
        self.choice = QComboBox(); layout.addWidget(self.choice)
        self.feedback = QLabel(); self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter); self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.keyboard = PianoKeyboard(); layout.addWidget(self.keyboard)
        buttons = QHBoxLayout()
        for label, action in (("Submit", self._submit), ("Clear notes", self._clear), ("Next", self.new_question)):
            button = QPushButton(label); button.clicked.connect(action); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.kind.currentIndexChanged.connect(self.new_question)
        self.training_mode.currentIndexChanged.connect(self._show_question)
        self.keyboard.note_changed.connect(controller.demo_note)
        controller.notes_changed.connect(self._notes_changed)
        controller.event_received.connect(self._event_received)
        QShortcut(QKeySequence("Return"), self, activated=self._submit)
        QShortcut(QKeySequence("N"), self, activated=self.new_question)
        self.new_question()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event); self._active = True
        self._notes_changed(self.controller.pressed_notes); self.started = time.monotonic()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._active = False; super().hideEvent(event)

    def new_question(self) -> None:
        if self.active_notes:
            self.feedback.setText("Release or clear all keys first."); return
        if self.question is not None and self.completed >= self.question_limit:
            self.feedback.setText(f"Question goal reached ({self.question_limit}). Review the Progress page."); return
        self.question = self.generator.question(self.kind.canonicalText())
        self.sequence.clear(); self.scored = False; self.last_correct = False
        self.started = time.monotonic(); self._show_question()

    def _show_question(self) -> None:
        if self.question is None:
            return
        self.prompt.setText(self.question.prompt)
        learn = self.training_mode.canonicalText() == "Learn"
        self.expected.setText(f"Answer: {self.question.answer_text}" if learn else "Answer: —")
        instruction = "Choose the answer, then submit." if self.question.options else "Play the answer, then submit."
        self.feedback.setText(instruction)
        self.choice.clear(); self.choice.addItems(self.question.options); self.choice.setVisible(bool(self.question.options))
        self.keyboard.set_expected(self.question.expected_pitch_classes if learn else frozenset())
        self.keyboard.set_notes(frozenset()); self.played.setText("—")

    def _event_received(self, payload: dict) -> None:
        if not self._active or self.question is None or not self.question.expected_sequence:
            return
        event = payload["event"]
        if event.event_type == "note_on" and event.velocity > 0 and event.note is not None:
            self.sequence.append(event.note)
            self.played.setText(" ".join(midi_note_name(note) for note in self.sequence))

    def _notes_changed(self, notes: frozenset[int]) -> None:
        if not self._active:
            return
        changed = notes != self.active_notes; self.active_notes = notes; self.keyboard.set_notes(notes)
        if self.question and not self.question.expected_sequence and not self.question.options:
            self.played.setText(" ".join(midi_note_name(note) for note in sorted(notes)) or "—")
        if changed and self.scored and not self.last_correct:
            self.scored = False

    def _submit(self) -> None:
        if self.question is None or self.scored:
            return
        if self.question.options:
            played = self.choice.canonicalText(); correct = check_answer(self.question, played)
        else:
            notes = self.sequence if self.question.expected_sequence else tuple(self.active_notes)
            if not notes:
                self.feedback.setText("Play an answer first."); return
            played = " ".join(map(str, notes)); correct = check_notes(self.question, notes)
        response = max(0, round((time.monotonic() - self.started) * 1000))
        try:
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="theory_practice",
                skill=self.question.kind.lower().replace(" ", "_"), question=self.question.prompt,
                expected=self.question.answer_text, played=played, correct=correct, response_time_ms=response,
                metadata={"mode": self.training_mode.canonicalText()},
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"The answer was not saved.\n\n{exc}"); return
        self.scored = True
        self.last_correct = correct
        self.completed += 1
        if self.training_mode.canonicalText() == "Test":
            self.feedback.setText("Correct — recorded." if correct else "Incorrect — recorded without hints.")
        else:
            self.feedback.setText("Correct" if correct else f"Wrong · Expected: {self.question.answer_text}")
            self.expected.setText(f"Answer: {self.question.answer_text}")
            self.keyboard.set_expected(self.question.expected_pitch_classes)
        self.attempt_recorded.emit()

    def _clear(self) -> None:
        for note in tuple(self.controller.pressed_notes):
            self.controller.demo_note(note, False)
        self.sequence.clear(); self.active_notes = frozenset(); self.played.setText("—")
        self.keyboard.set_notes(frozenset())
        if not self.last_correct:
            self.scored = False
