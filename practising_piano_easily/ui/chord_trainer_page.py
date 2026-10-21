"""Interactive chord-construction page."""

from __future__ import annotations

import sqlite3
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QSpinBox, QVBoxLayout, QWidget)
from .localized_widgets import (QCheckBox, QComboBox, QLabel, QMessageBox, QPushButton)

from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.chord_construction import (
    ChordConstructionTrainer, Evaluation, match_chord, midi_note_name, pitch_name,
)

from .keyboard_widget import PianoKeyboard


class ChordTrainerPage(QWidget):
    attempt_recorded = Signal()

    def __init__(self, controller: MidiController, database: Database, session_id: int) -> None:
        super().__init__()
        self.controller = controller
        self._active = False
        self.question_limit = 20
        self.trainer = ChordConstructionTrainer(database, session_id)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._evaluate)
        self.advance_timer = QTimer(self)
        self.advance_timer.setSingleShot(True)
        self.advance_timer.timeout.connect(self.next_question)
        self._await_release = False

        layout = QVBoxLayout(self)
        heading = QLabel("Chord Construction")
        heading.setStyleSheet("font-size: 26px; font-weight: 700")
        layout.addWidget(heading)
        controls = QHBoxLayout()
        self.training_mode = QComboBox()
        self.training_mode.addItems(["Learn", "Practice", "Test"])
        self.training_mode.setCanonicalText("Learn")
        self.trainer.training_mode = "Learn"
        self.mode = QComboBox()
        self.mode.addItems(["Root Position", "Any Inversion"])
        self.level = QComboBox()
        self.level.addItems([
            "Level 1 · Major / minor", "Level 2 · Diminished / augmented",
            "Level 3 · Common sevenths", "Level 4 · Advanced sevenths",
            "Level 5 · Sus / add / 6", "Level 6 · Ninth chords",
            "Level 7 · 11 / 13", "Level 8 · Altered dominants",
        ])
        self.settling = QSpinBox()
        self.settling.setRange(150, 800)
        self.settling.setValue(300)
        self.settling.setSuffix(" ms")
        controls.addWidget(QLabel("Training:"))
        controls.addWidget(self.training_mode)
        controls.addWidget(QLabel("Voicing:"))
        controls.addWidget(self.mode)
        controls.addSpacing(20)
        controls.addWidget(QLabel("Level:"))
        controls.addWidget(self.level)
        controls.addSpacing(20)
        controls.addWidget(QLabel("Settling:"))
        controls.addWidget(self.settling)
        controls.addStretch()
        layout.addLayout(controls)
        checking = QHBoxLayout()
        self.slow_practice = QCheckBox("Wait for the complete chord · no time limit · automatic confirmation")
        self.slow_practice.setChecked(True)
        checking.addWidget(self.slow_practice)
        checking.addStretch()
        layout.addLayout(checking)

        target_heading = QLabel("Target chord · read first, then play")
        target_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(target_heading)
        self.chord = QLabel()
        self.chord.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chord.setStyleSheet("font-size: 64px; font-weight: 800; margin: 12px")
        layout.addWidget(self.chord)
        info = QGridLayout()
        self.played = QLabel("—")
        self.expected = QLabel("—")
        self.formula = QLabel("—")
        info.addWidget(QLabel("Currently played:"), 0, 0)
        info.addWidget(self.played, 0, 1)
        info.addWidget(QLabel("Expected:"), 1, 0)
        info.addWidget(self.expected, 1, 1)
        info.addWidget(QLabel("Formula:"), 2, 0)
        info.addWidget(self.formula, 2, 1)
        layout.addLayout(info)
        self.feedback = QLabel("Play the chord. The answer appears after scoring.")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("font-size: 18px; font-weight: 700; padding: 8px")
        layout.addWidget(self.feedback)
        self.details = QLabel()
        self.details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.keyboard = PianoKeyboard()
        layout.addWidget(self.keyboard)
        demo_hint = QLabel("Demo mode: click piano keys to toggle them on or off. MIDI input remains the primary practice method.")
        demo_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        demo_hint.setStyleSheet("color: #64748b")
        layout.addWidget(demo_hint)
        self.stats = QLabel()
        self.stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats)
        next_button = QPushButton("Next (N)")
        next_button.clicked.connect(self.next_question)
        layout.addWidget(next_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.keyboard.note_changed.connect(controller.demo_note)
        controller.notes_changed.connect(self._notes_changed)
        self.slow_practice.toggled.connect(self._checking_changed)
        self.training_mode.currentIndexChanged.connect(self._training_mode_changed)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.level.currentIndexChanged.connect(lambda index: self._level_changed(index + 1))
        QShortcut(QKeySequence("N"), self, activated=self.next_question)
        self._checking_changed()
        self._show_question()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._active = True
        self._await_release = bool(self.controller.pressed_notes)
        self._notes_changed(self.controller.pressed_notes)
        if not self.trainer.active_notes and not self.trainer.attempt_scored:
            self.trainer.question_started = time.monotonic()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._active = False
        self.timer.stop()
        self.advance_timer.stop()
        super().hideEvent(event)

    def _mode_changed(self) -> None:
        self.trainer.any_inversion = self.mode.currentIndex() == 1
        self._preview()

    def _checking_changed(self) -> None:
        self.timer.stop()
        self.trainer.slow_practice = self.slow_practice.isChecked()
        if self._active:
            self._preview()

    def _training_mode_changed(self) -> None:
        if self.trainer.active_notes:
            self.training_mode.blockSignals(True)
            self.training_mode.setCanonicalText(self.trainer.training_mode)
            self.training_mode.blockSignals(False)
            self.feedback.setText("Release all keys before changing training mode.")
            return
        self.trainer.training_mode = self.training_mode.canonicalText()
        self._show_question()

    def _level_changed(self, level: int) -> None:
        if self.trainer.active_notes:
            self.level.blockSignals(True)
            self.level.setCurrentIndex(self.trainer.level - 1)
            self.level.blockSignals(False)
            self.feedback.setText("Release all keys before changing level.")
            return
        self.timer.stop()
        self.trainer.set_level(level)
        self._show_question()

    def _notes_changed(self, notes: frozenset[int]) -> None:
        if not self._active:
            return
        self.played.setText(" ".join(midi_note_name(note, self.trainer.current_chord) for note in sorted(notes)) or "—")
        self.keyboard.set_notes(notes)
        self.timer.stop()
        self.advance_timer.stop()
        if self._await_release:
            self._await_release = bool(notes)
            if notes:
                self.feedback.setText("Release all keys first. The target is already shown above.")
            else:
                action = self.trainer.set_active_notes(frozenset())
                if action == "advance":
                    self.next_question()
                else:
                    self._show_question()
            return
        action = self.trainer.set_active_notes(notes)
        total = self.trainer.correct_count + self.trainer.wrong_count
        if not notes and total >= self.question_limit:
            self.timer.stop()
            self.feedback.setText(f"Question goal reached ({self.question_limit}). Review Progress or press Next to continue.")
        elif action == "settle":
            self._preview()
        elif action == "advance":
            self.advance_timer.start(500)
        elif action == "released":
            self._show_question()

    def _preview(self) -> None:
        self.timer.stop()
        notes = self.trainer.active_notes
        if not self._active or not notes or self.trainer.attempt_scored or self._await_release:
            return
        result = match_chord(self.trainer.current_chord, notes, self.trainer.any_inversion)
        if self.trainer.training_mode != "Test":
            self.keyboard.set_notes(notes,
                correct=frozenset(note for note in notes if note % 12 in result.expected_pitch_classes),
                incorrect=frozenset(note for note in notes if note % 12 in result.extra_pitch_classes))
        self.feedback.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a; padding: 8px")
        self.details.clear()
        if result.correct:
            self.feedback.setText("Target complete. Confirming automatically…")
        elif self.trainer.training_mode == "Test":
            self.feedback.setText("Listening…")
        else:
            chord = self.trainer.current_chord
            lines = []
            if result.extra_pitch_classes:
                lines.append("Release extra notes: " + " ".join(pitch_name(pc, chord) for pc in sorted(result.extra_pitch_classes)))
            if result.missing_pitch_classes:
                lines.append("Still needed: " + " ".join(pitch_name(pc, chord) for pc in sorted(result.missing_pitch_classes)))
            if not result.missing_pitch_classes and not result.extra_pitch_classes and not result.correct:
                lines.append(f"Lowest note must be the slash bass ({chord.bass})." if chord.bass else f"Lowest note must be the root ({chord.root}).")
            self.feedback.setText(" · ".join(lines))
            self.details.setText("Keep the correct keys held. Correct the others; no Check button is needed.")
        if result.correct or not self.trainer.slow_practice or self.trainer.training_mode == "Test":
            self.timer.start(self.settling.value())

    def _evaluate(self) -> None:
        if not self._active or self._await_release:
            return
        if not self.trainer.active_notes:
            return
        if (self.trainer.slow_practice and self.trainer.training_mode != "Test"
                and not match_chord(self.trainer.current_chord, self.trainer.active_notes, self.trainer.any_inversion).correct):
            self._preview()
            return
        try:
            result = self.trainer.evaluate()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"The attempt was not saved and was not scored.\n\n{exc}")
            return
        if result is None:
            return
        self._show_result(result)
        self._show_stats()
        self.attempt_recorded.emit()

    def _show_result(self, result: Evaluation) -> None:
        chord = self.trainer.current_chord
        if self.trainer.training_mode == "Test":
            self.keyboard.set_expected(frozenset())
            self.keyboard.set_notes(frozenset(result.played_notes))
            self.expected.setText("—")
            self.formula.setText("—")
            self.feedback.setText("Correct — recorded." if result.correct else "Incorrect — recorded without hints.")
            color = "#15803d" if result.correct else "#b91c1c"
            self.feedback.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color}; padding: 8px")
            self.details.setText(f"Response: {result.response_time_ms / 1000:.2f} s")
            return
        self.keyboard.set_expected(result.expected_pitch_classes)
        self.expected.setText(" ".join(map(str, chord.notes)))
        self.formula.setText(" ".join(chord.formula).replace("b", "♭").replace("#", "♯"))
        correct_notes = frozenset(note for note in result.played_notes if note % 12 in result.expected_pitch_classes)
        incorrect_notes = frozenset(note for note in result.played_notes if note % 12 in result.extra_pitch_classes)
        self.keyboard.set_notes(frozenset(result.played_notes), correct=correct_notes, incorrect=incorrect_notes)
        if result.correct:
            self.feedback.setText("Correct")
            self.feedback.setStyleSheet("font-size: 18px; font-weight: 700; color: #15803d; padding: 8px")
            instruction = "Release all keys for the next chord."
            self.details.setText(f"Response: {result.response_time_ms / 1000:.2f} s · {instruction}")
            return
        lines = []
        if result.missing_pitch_classes:
            lines.append("Missing: " + " ".join(pitch_name(pc, chord) for pc in sorted(result.missing_pitch_classes)))
        if result.extra_pitch_classes:
            lines.append("Extra: " + " ".join(pitch_name(pc, chord) for pc in sorted(result.extra_pitch_classes)))
        if (not result.missing_pitch_classes and not result.extra_pitch_classes
                and not result.root_position_ok and chord.bass is None):
            lines.append(f"Lowest note must be the root ({chord.root}).")
        if not result.bass_ok and chord.bass:
            lines.append(f"Lowest note must be the slash bass ({chord.bass}).")
        if len(result.missing_pitch_classes) == len(result.extra_pitch_classes) == 1:
            lines.append(
                f"{pitch_name(next(iter(result.extra_pitch_classes)), chord)} should be "
                f"{pitch_name(next(iter(result.missing_pitch_classes)), chord)}."
            )
        lines.append("Release all keys, then try the same chord again.")
        self.feedback.setText("Wrong")
        self.feedback.setStyleSheet("font-size: 18px; font-weight: 700; color: #b91c1c; padding: 8px")
        self.details.setText(" · ".join(lines))

    def next_question(self) -> None:
        if self.trainer.active_notes:
            self.feedback.setText("Release all keys before moving to the next chord.")
            return
        self.timer.stop()
        self.advance_timer.stop()
        self.trainer.next_question()
        self._show_question()

    def _show_question(self) -> None:
        self.timer.stop()
        self.advance_timer.stop()
        chord = self.trainer.current_chord
        self.chord.setText(chord.symbol)
        learn = self.trainer.training_mode == "Learn"
        self.expected.setText(" ".join(map(str, chord.notes)) if learn else "—")
        self.formula.setText(" ".join(chord.formula).replace("b", "♭").replace("#", "♯") if learn else "—")
        self.feedback.setText("Read the target first. Add notes at your own pace; a complete chord is confirmed automatically." if learn else "Play the target chord. Confirmation is automatic.")
        self.feedback.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a; padding: 8px")
        self.details.clear()
        self.keyboard.set_expected(chord.pitch_classes if learn else frozenset())
        self.keyboard.set_notes(frozenset())
        self._show_stats()

    def _show_stats(self) -> None:
        trainer = self.trainer
        self.stats.setText(
            f"Without corrections: {trainer.correct_count}    Corrected / wrong: {trainer.wrong_count}    "
            f"Accuracy: {trainer.accuracy:.1f}%    Average response: {trainer.average_response_ms / 1000:.1f} s"
        )
