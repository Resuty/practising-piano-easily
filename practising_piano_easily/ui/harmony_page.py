"""Diatonic reference, layered harmony analysis, and progression practice."""

from __future__ import annotations

import sqlite3
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QTextEdit)

from practising_piano_easily.core import analyze_progression, diatonic_chords, parse_key
from practising_piano_easily.core import measure_voice_leading
from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.chord_construction import midi_note_name
from practising_piano_easily.trainers.progression import ProgressionTrainer

from .keyboard_widget import PianoKeyboard


KEYS = [f"{root} {mode}" for mode in ("major", "minor") for root in
        ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")]


class HarmonyPage(QTabWidget):
    attempt_recorded = Signal()

    def __init__(self, controller: MidiController, database: Database, session_id: int) -> None:
        super().__init__()
        self.addTab(HarmonyAnalysis(), "Analyze")
        practice = ProgressionPractice(controller, database, session_id)
        practice.attempt_recorded.connect(self.attempt_recorded)
        self.addTab(practice, "Progression Practice")


class HarmonyAnalysis(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Harmony")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        form = QFormLayout()
        self.key = QComboBox()
        self.key.addItems(KEYS)
        self.symbols = QLineEdit("Cmaj7 A7 Dm7 G7")
        form.addRow("Key candidate:", self.key)
        form.addRow("Chord symbols:", self.symbols)
        layout.addLayout(form)
        analyze = QPushButton("Analyze")
        analyze.clicked.connect(self._analyze)
        layout.addWidget(analyze)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self._analyze()

    def _analyze(self) -> None:
        try:
            key = parse_key(self.key.canonicalText())
            symbols = self.symbols.text().split()
            findings = analyze_progression(symbols, key)
            diatonic = diatonic_chords(key, sevenths=True)
        except ValueError as exc:
            self.output.setPlainText(f"Invalid input: {exc}")
            return
        lines = [f"Key candidate: {key.name}", "", "Diatonic sevenths:",
                 "  ".join(f"{item.roman}={item.chord.symbol}" for item in diatonic), "", "Analysis:"]
        for finding in findings:
            label = finding.roman or "unclassified"
            fact = "chromatic" if finding.chromatic else "diatonic"
            lines.append(f"{finding.chord_symbol}: {label} [{fact}]")
            for interpretation in finding.possible_interpretations:
                lines.append(f"  Possible interpretation: {interpretation}")
        self.output.setPlainText("\n".join(lines))


class ProgressionPractice(QWidget):
    attempt_recorded = Signal()

    def __init__(self, controller: MidiController, database: Database, session_id: int) -> None:
        super().__init__()
        self.controller = controller
        self.database = database
        self.session_id = session_id
        self.progression: ProgressionTrainer | None = None
        self.active_notes: frozenset[int] = frozenset()
        self.scored = False
        self.last_correct = False
        self.started = time.monotonic()
        self.previous_voicing: tuple[int, ...] | None = None
        self._active = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._evaluate)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.key = QComboBox()
        self.key.addItems(KEYS)
        self.romans = QLineEdit("I V vi IV")
        self.voicing = QComboBox()
        self.voicing.addItems(["Free voicing", "Root position"])
        form.addRow("Key:", self.key)
        form.addRow("Progression:", self.romans)
        form.addRow("Voicing:", self.voicing)
        layout.addLayout(form)
        start = QPushButton("Start / Restart")
        start.clicked.connect(self._configure)
        layout.addWidget(start)
        self.question = QLabel()
        self.question.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question.setStyleSheet("font-size: 42px; font-weight: 800; padding: 12px")
        layout.addWidget(self.question)
        self.answer = QLabel("—")
        self.answer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.answer)
        self.feedback = QLabel("Configure a progression, then play each chord in order.")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.keyboard = PianoKeyboard()
        layout.addWidget(self.keyboard)
        self.keyboard.note_changed.connect(controller.demo_note)
        controller.notes_changed.connect(self._notes_changed)
        self._configure()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._active = True
        self._notes_changed(self.controller.pressed_notes)
        self.started = time.monotonic()
        self.previous_voicing = None

    def hideEvent(self, event) -> None:  # noqa: N802
        self._active = False
        self.timer.stop()
        super().hideEvent(event)

    def _configure(self) -> None:
        if self.active_notes:
            self.feedback.setText("Release all keys before restarting.")
            return
        try:
            self.progression = ProgressionTrainer(parse_key(self.key.canonicalText()), self.romans.text().split())
        except ValueError as exc:
            self.feedback.setText(f"Invalid progression: {exc}")
            return
        self.scored = False
        self.last_correct = False
        self.started = time.monotonic()
        self._show_question()

    def _notes_changed(self, notes: frozenset[int]) -> None:
        if not self._active or self.progression is None:
            return
        changed = notes != self.active_notes
        self.active_notes = notes
        self.keyboard.set_notes(notes)
        if notes and changed and not self.scored:
            self.feedback.setText("Listening…")
            self.timer.start(300)
        elif not notes:
            self.timer.stop()
            if self.scored and self.last_correct:
                complete = self.progression.advance()
                if complete:
                    self.previous_voicing = None
                self.feedback.setText("Progression complete. Starting again." if complete else "Correct. Next chord.")
                self.scored = False
                self.last_correct = False
                self.started = time.monotonic()
                QTimer.singleShot(450, self._show_question)
            elif self.scored:
                self.scored = False

    def _evaluate(self) -> None:
        if self.progression is None or not self.active_notes or self.scored:
            return
        result = self.progression.check(self.active_notes, self.voicing.currentIndex() == 0)
        elapsed = max(0, round((time.monotonic() - self.started) * 1000))
        try:
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="progression", skill="roman_numeral",
                question=f"{self.progression.key.name}: {self.progression.current_roman}",
                expected=self.progression.current_chord.symbol,
                played=" ".join(map(str, sorted(self.active_notes))), correct=result.correct,
                response_time_ms=elapsed, metadata={"progression": self.progression.romans},
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"The attempt was not saved.\n\n{exc}")
            return
        self.scored = True
        self.last_correct = result.correct
        self.answer.setText(f"Expected: {self.progression.current_chord.symbol} = " +
                            " ".join(map(str, self.progression.current_chord.notes)))
        self.keyboard.set_expected(self.progression.current_chord.pitch_classes)
        if result.correct:
            movement = ""
            current_voicing = tuple(sorted(self.active_notes))
            if self.previous_voicing:
                metrics = measure_voice_leading(self.previous_voicing, current_voicing)
                movement = (
                    f" · Movement: {metrics.total_movement} · Largest leap: {metrics.largest_leap} "
                    f"· Common tones: {metrics.common_tones_retained}"
                )
            self.previous_voicing = current_voicing
            self.feedback.setText(f"Correct{movement} · Release all keys.")
        else:
            self.feedback.setText("Wrong · Release all keys and retry this chord.")
        self.attempt_recorded.emit()

    def _show_question(self) -> None:
        if self.progression is None:
            return
        self.question.setText(f"{self.progression.key.name}  ·  {self.progression.current_roman}")
        self.answer.setText("—")
        self.keyboard.set_expected(frozenset())
        self.keyboard.set_notes(frozenset())
