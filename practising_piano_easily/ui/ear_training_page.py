"""Ear-training UI backed by the internal synthesizer."""

from __future__ import annotations

import sqlite3
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QSlider, QSpinBox, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QFormLayout, QLabel, QMessageBox, QPushButton)

from practising_piano_easily.audio import Synthesizer
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.ear_training import EarQuestion, EarTrainer


class EarTrainingPage(QWidget):
    attempt_recorded = Signal()

    def __init__(self, database: Database, session_id: int) -> None:
        super().__init__()
        self.database = database
        self.session_id = session_id
        self.trainer = EarTrainer()
        self.synth = Synthesizer()
        self.question: EarQuestion | None = None
        self.replays = 0
        self.answered = False
        self.completed = 0
        self.question_limit = 20
        self.started = time.monotonic()

        layout = QVBoxLayout(self)
        title = QLabel("Ear Training")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Block", "Mixed (Stage 1)"])
        self.exercise = QComboBox()
        self.exercise.addItems(["Interval", "Major vs minor", "Triad quality", "Seventh quality",
                                "Inversion", "Bass note", "Root movement", "Cadence"])
        self.replay_limit = QSpinBox()
        self.replay_limit.setRange(1, 10)
        self.replay_limit.setValue(3)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(25)
        form.addRow("Mode:", self.mode)
        form.addRow("Block exercise:", self.exercise)
        form.addRow("Replay limit:", self.replay_limit)
        form.addRow("Volume:", self.volume)
        layout.addLayout(form)

        self.prompt = QLabel()
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setStyleSheet("font-size: 24px; font-weight: 700; padding: 18px")
        layout.addWidget(self.prompt)
        controls = QHBoxLayout()
        self.play_button = QPushButton("Play / Replay (Space)")
        self.answer = QComboBox()
        self.submit_button = QPushButton("Submit (Enter)")
        self.next_button = QPushButton("Next (N)")
        controls.addWidget(self.play_button)
        controls.addWidget(self.answer, 1)
        controls.addWidget(self.submit_button)
        controls.addWidget(self.next_button)
        layout.addLayout(controls)
        self.feedback = QLabel("Press Play to hear the question.")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback.setStyleSheet("font-size: 18px; padding: 20px")
        layout.addWidget(self.feedback)
        layout.addStretch()

        self.play_button.clicked.connect(self._play)
        self.submit_button.clicked.connect(self._submit)
        self.next_button.clicked.connect(self.new_question)
        self.mode.currentIndexChanged.connect(self.new_question)
        self.exercise.currentIndexChanged.connect(self.new_question)
        self.replay_limit.valueChanged.connect(self._update_play_button)
        QShortcut(QKeySequence("Space"), self, activated=self._play)
        QShortcut(QKeySequence("Return"), self, activated=self._submit)
        QShortcut(QKeySequence("N"), self, activated=self.new_question)
        self.new_question()

    def new_question(self) -> None:
        if self.question is not None and self.completed >= self.question_limit:
            self.feedback.setText(f"Question goal reached ({self.question_limit}). Review the Progress page.")
            return
        kind = "Mixed (Stage 1)" if self.mode.currentIndex() == 1 else self.exercise.canonicalText()
        self.question = self.trainer.question(kind)
        self.answer.clear()
        self.answer.addItems(self.question.options)
        self.prompt.setText(self.question.prompt)
        self.feedback.setText("Press Play to hear the question.")
        self.replays = 0
        self.answered = False
        self.started = time.monotonic()
        self._update_play_button()

    def _play(self) -> None:
        if self.question is None or self.replays >= self.replay_limit.value():
            return
        try:
            self.synth.play(self.question.groups, self.volume.value() / 100)
        except Exception as exc:
            self.feedback.setText(f"Audio device unavailable: {exc}")
            return
        self.replays += 1
        self.feedback.setText("Listen, then choose an answer.")
        self._update_play_button()

    def _update_play_button(self) -> None:
        self.play_button.setText(f"Play / Replay (Space)  {self.replays}/{self.replay_limit.value()}")
        self.play_button.setEnabled(self.replays < self.replay_limit.value())

    def _submit(self) -> None:
        if self.question is None or self.answered:
            return
        played = self.answer.canonicalText()
        correct = played == self.question.answer
        response = max(0, round((time.monotonic() - self.started) * 1000))
        try:
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="ear_training",
                skill=self.question.kind.lower().replace(" ", "_"), question=self.question.prompt,
                expected=self.question.answer, played=played, correct=correct,
                response_time_ms=response,
                metadata={"groups": self.question.groups, "replays": self.replays},
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"The answer was not saved.\n\n{exc}")
            return
        self.answered = True
        self.completed += 1
        self.feedback.setText(
            f"Correct · {response / 1000:.2f} s" if correct
            else f"Wrong · Expected: {self.question.answer}"
        )
        self.attempt_recorded.emit()
