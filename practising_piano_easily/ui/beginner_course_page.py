"""Guided lessons with a native score, exact MIDI following and resumable progress."""

import sqlite3
import time

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QScrollArea, QProgressBar

from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES, ScoreFollower, completed_lessons, next_lesson_index
from practising_piano_easily.trainers.chord_construction import midi_note_name

from .localized_widgets import QLabel, QPushButton, QComboBox, QCheckBox, QMessageBox
from .keyboard_widget import PianoKeyboard
from .score_widget import ScoreWidget


class BeginnerCoursePage(QWidget):
    attempt_recorded = Signal()
    midi_setup_requested = Signal()
    falling_requested = Signal(object)

    def __init__(self, controller, database, session_id, synth):
        super().__init__()
        self.controller, self.database, self.session_id, self.synth = controller, database, session_id, synth
        self._active = False
        self._running = False
        self._saved = False
        self._started = time.monotonic()
        self.follower = ScoreFollower(LESSONS[0])
        self._items = LESSONS
        layout = QVBoxLayout(self)
        title = QLabel("Beginner course & sheet music")
        title.setStyleSheet("font-size: 24px; font-weight: 700")
        layout.addWidget(title)
        top = QHBoxLayout()
        self.course_progress = QLabel()
        top.addWidget(self.course_progress)
        top.addStretch()
        falling = QPushButton("Play with falling notes")
        falling.clicked.connect(lambda: self.falling_requested.emit(self.lesson))
        top.addWidget(falling)
        setup = QPushButton("Connect MIDI keyboard")
        setup.clicked.connect(self.midi_setup_requested)
        top.addWidget(setup)
        layout.addLayout(top)
        self.device_status = QLabel("Use a MIDI keyboard, or click the on-screen keys for demo.")
        self.device_status.setWordWrap(True)
        layout.addWidget(self.device_status)
        row = QHBoxLayout()
        self.collection = QComboBox()
        self.collection.addItems(["Courses · 24 lessons", "Repertoire · 12 pieces"])
        self.collection.currentIndexChanged.connect(self._collection_changed)
        row.addWidget(self.collection)
        previous = QPushButton("Previous lesson")
        previous.clicked.connect(lambda: self.lesson_picker.setCurrentIndex(max(0, self.lesson_picker.currentIndex() - 1)))
        self.lesson_picker = QComboBox()
        self.lesson_picker.addItems([lesson.title for lesson in LESSONS])
        self.lesson_picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.lesson_picker.setMinimumContentsLength(16)
        self.next_button = QPushButton("Next lesson")
        self.next_button.clicked.connect(self._next_lesson)
        row.addWidget(previous)
        row.addWidget(self.lesson_picker, 1)
        row.addWidget(self.next_button)
        layout.addLayout(row)
        self.instructions = QLabel()
        self.instructions.setWordWrap(True)
        self.instructions.setStyleSheet("font-size: 14px; padding: 5px; background: #eaf2f8; color: #172033;")
        layout.addWidget(self.instructions)
        self.score = ScoreWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(262)
        scroll.setWidget(self.score)
        layout.addWidget(scroll, 2)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start / restart slow practice")
        self.start_button.clicked.connect(self.start_practice)
        play = QPushButton("Listen to score")
        play.clicked.connect(self._play_score)
        self.show_names = QCheckBox("Show note names")
        self.show_names.setChecked(True)
        self.show_names.toggled.connect(self._update_names)
        controls.addWidget(self.start_button)
        controls.addWidget(play)
        controls.addWidget(self.show_names)
        controls.addStretch()
        self.previous_line = QPushButton("Previous score line")
        self.previous_line.clicked.connect(lambda: self.score.set_page(self.score.page - 1))
        self.line_number = QLabel()
        self.next_line = QPushButton("Next score line")
        self.next_line.clicked.connect(lambda: self.score.set_page(self.score.page + 1))
        controls.addWidget(self.previous_line)
        controls.addWidget(self.line_number)
        controls.addWidget(self.next_line)
        self.score.page_changed.connect(self._line_changed)
        layout.addLayout(controls)
        self.target = QLabel()
        self.target.setWordWrap(True)
        self.target.setStyleSheet("font-size: 16px; font-weight: 600")
        layout.addWidget(self.target)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.keyboard = PianoKeyboard(36, 84)
        self.keyboard.setMinimumHeight(90)
        self.keyboard.setMaximumHeight(120)
        self.keyboard.note_changed.connect(controller.demo_note)
        layout.addWidget(self.keyboard, 1)
        layout.addWidget(QLabel("Yellow = target · Blue = pressed · Green = correct · Red = extra. Match the written octave; timing is not graded."))
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.save_button = QPushButton("Retry saving this completed lesson")
        self.save_button.clicked.connect(self._save_completion)
        self.save_button.hide()
        layout.addWidget(self.save_button)
        controller.notes_changed.connect(self._notes_changed)
        controller.status_changed.connect(self.device_status.setText)
        self.lesson_picker.currentIndexChanged.connect(self._select_lesson)
        self.resume_next()

    @property
    def lesson(self):
        return self._items[self.lesson_picker.currentIndex()]

    def _collection_changed(self):
        self._items = PIECES if self.collection.currentIndex() else LESSONS
        with QSignalBlocker(self.lesson_picker):
            self.lesson_picker.clear()
            self.lesson_picker.addItems([item.title for item in self._items])
        self._select_lesson()

    def resume_next(self):
        with QSignalBlocker(self.collection):
            self.collection.setCurrentIndex(0)
        self._items = LESSONS
        index = next_lesson_index(self.database)
        with QSignalBlocker(self.lesson_picker):
            self.lesson_picker.clear()
            self.lesson_picker.addItems([lesson.title for lesson in LESSONS])
            self.lesson_picker.setCurrentIndex(index)
        self._select_lesson()

    def _select_lesson(self):
        self._running = False
        self._saved = False
        self.follower = ScoreFollower(self.lesson)
        self.instructions.setText(self.lesson.instructions)
        self.feedback.setText("Listen or read first, then start slow practice. You may correct keys at any time.")
        self.progress_bar.setRange(0, len(self.lesson.steps))
        self.progress_bar.setValue(0)
        self.save_button.hide()
        self.refresh_progress()
        self._render_target()

    def refresh_progress(self):
        completed = completed_lessons(self.database)
        count = len(completed & {lesson.id for lesson in LESSONS})
        songs = len(completed & {piece.id for piece in PIECES})
        self.course_progress.setText(f"Lessons completed: {count} / {len(LESSONS)} · Pieces completed: {songs} / {len(PIECES)}")
        self.next_button.setEnabled((self.lesson.id in completed or bool(self.collection.currentIndex()))
                                   and self.lesson_picker.currentIndex() < len(self._items) - 1)

    def _next_lesson(self):
        self.lesson_picker.setCurrentIndex(min(len(self._items) - 1, self.lesson_picker.currentIndex() + 1))

    def _line_changed(self):
        self.line_number.setText(f"{self.score.page + 1} / {self.score.page_count}")
        self.previous_line.setEnabled(self.score.page > 0)
        self.next_line.setEnabled(self.score.page < self.score.page_count - 1)

    def showEvent(self, event):
        super().showEvent(event)
        self._active = True
        self.refresh_progress()
        self._notes_changed(self.controller.pressed_notes)

    def hideEvent(self, event):
        self._active = False
        self._running = False
        if not self.follower.finished:
            self.feedback.setText("Practice paused. Press Start to begin this lesson again.")
        super().hideEvent(event)

    def start_practice(self):
        if self.controller.pressed_notes:
            self.feedback.setText("Release or clear all keys first.")
            return
        self.follower = ScoreFollower(self.lesson)
        self._saved = False
        self._running = True
        self._started = time.monotonic()
        self.progress_bar.setValue(0)
        self.save_button.hide()
        self.feedback.setText("Take your time. Play the blue score position, then release all keys.")
        self._render_target()

    def _update_names(self, checked):
        self.score.show_names = checked
        self.score.update()
        self.keyboard.show_note_names = checked
        self._render_target()

    def _render_target(self):
        self.score.set_score(self.lesson, self.follower.index, self.follower.matched)
        notes = self.follower.expected
        self.keyboard.set_expected_notes(notes)
        self.keyboard.set_notes(self.controller.pressed_notes)
        if self.follower.finished:
            self.target.setText("Lesson complete. Continue when you are ready.")
        elif self.show_names.isChecked():
            step = self.lesson.steps[self.follower.index]
            right = " ".join(midi_note_name(note) for note in step.right) or "—"
            left = " ".join(midi_note_name(note) for note in step.left) or "—"
            self.target.setText(f"Right hand: {right}  ·  Left hand: {left}")
        else:
            self.target.setText("Follow the blue position on the score.")

    def _notes_changed(self, notes):
        if not self._active:
            return
        expected = self.follower.expected
        self.keyboard.set_notes(notes, correct=notes & expected, incorrect=notes - expected)
        if not self._running:
            return
        state = self.follower.update(notes)
        if state == "finished":
            self._running = False
            self.progress_bar.setValue(len(self.lesson.steps))
            self._render_target()
            self._save_completion()
        elif state == "advanced":
            self.progress_bar.setValue(self.follower.index)
            self._render_target()
            self.feedback.setText("Next position. Take your time.")
        elif state in {"matched", "release"}:
            self.score.set_score(self.lesson, self.follower.index, True)
            self.feedback.setText("Correct. Release this group of keys to continue.")
        elif state == "extra":
            names = " ".join(midi_note_name(note) for note in sorted(notes - expected))
            self.feedback.setText(f"Release extra notes: {names}. You can keep the correct keys held.")
        else:
            names = " ".join(midi_note_name(note) for note in sorted(expected - notes))
            self.feedback.setText(f"Still needed: {names}. No rush.")

    def _save_completion(self):
        if self._saved or not self.follower.finished:
            return
        try:
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="beginner_course", skill="score_playing",
                question=self.lesson.id, expected=str([sorted(step.notes) for step in self.lesson.steps]),
                played="Completed all score positions", correct=self.follower.mistakes == 0,
                response_time_ms=max(0, round((time.monotonic() - self._started) * 1000)),
                metadata={"completed": True, "title": self.lesson.title,
                          "corrected_notes": self.follower.mistakes, "timing_graded": False},
            )
        except sqlite3.Error as exc:
            self.save_button.show()
            QMessageBox.critical(self, "Database error", f"The attempt was not saved.\n\n{exc}")
            return
        self._saved = True
        self.save_button.hide()
        self.feedback.setText(f"Completed! Notes corrected: {self.follower.mistakes}. You may repeat or continue to the next lesson.")
        self.refresh_progress()
        self.attempt_recorded.emit()

    def _play_score(self):
        if self._running:
            self._running = False
            self.feedback.setText("Practice paused. Press Start to begin this lesson again.")
        try:
            volume = int(self.database.get_setting("ear_volume", "25")) / 100
            groups = tuple((tuple(sorted(step.notes)), step.beats) for step in self.lesson.steps)
            self.synth.play_score(groups, tempo=80, volume=volume)
        except Exception as exc:
            self.feedback.setText(f"Audio device unavailable: {exc}")
