"""Bar-based, untimed score following with optional repeat after all keys are released."""

import sqlite3
import time

from PySide6.QtCore import Signal, Qt, QSignalBlocker
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSpinBox, QProgressBar, QStackedWidget, QLabel as PlainLabel

from practising_piano_easily.analysis.midi_file import load_midi
from practising_piano_easily.analysis.falling_score import load_falling_midi
from practising_piano_easily.trainers.midi_score import MidiScoreFollower
from practising_piano_easily.trainers.falling_notes import score_from_lesson
from practising_piano_easily.trainers.chord_construction import midi_note_name
from .localized_widgets import QLabel, QComboBox, QPushButton, QMessageBox, QCheckBox
from .keyboard_widget import PianoKeyboard
from .midi_notation_widget import MidiNotationWidget
from .notation_controls import NotationControls
from .hand_controls import HandControls
from .i18n import language, tr


class DownloadedScorePage(QWidget):
    attempt_recorded = Signal()
    falling_requested = Signal(object)
    lesson_falling_requested = Signal(object)
    score_opened = Signal(object)

    def __init__(self, controller, database, session_id):
        super().__init__()
        self.controller, self.database, self.session_id = controller, database, session_id
        self.summary = None
        self.source = None
        self.folder = None
        self.lesson = None
        self.follower = None
        self.groups = ()
        self.full_score = self._all_score = self._section = None
        self._offset = 0.0
        self._repeat_pending = False
        self._running = False
        self._saved = False
        self._active = False
        layout = QVBoxLayout(self)
        self.title = PlainLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        language.changed.connect(self._update_title)
        self._update_title()
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1)
        self.falling_button = QPushButton("Play with falling notes")
        self.falling_button.setEnabled(False)
        self.falling_button.clicked.connect(self._open_falling)
        title_row.addWidget(self.falling_button)
        layout.addLayout(title_row)
        explanation = self.explanation = QLabel("Read the original PDF; MIDI supplies the note order. Turn PDF pages yourself. This is pitch practice, not rhythm or fingering assessment.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.document = QPdfDocument(self)
        self.pdf = QPdfView(self)
        self.pdf.setDocument(self.document)
        self.pdf.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.score_views = QStackedWidget()
        self.score_views.addWidget(self.pdf)
        self.midi_staff = MidiNotationWidget(full_score=True)
        self.notation_controls = NotationControls(self.midi_staff, database, "reading_notation")
        notation_row = QHBoxLayout()
        self.score_mode = QComboBox()
        self.score_mode.addItems(["Practice score (MIDI)", "Original PDF"])
        self.score_mode.currentIndexChanged.connect(self._view_changed)
        notation_row.addWidget(self.notation_controls, 1)
        notation_row.addWidget(self.score_mode)
        layout.addLayout(notation_row)
        self.hands = HandControls(database, "reading")
        self.hands.changed.connect(self._hand_changed)
        layout.addWidget(self.hands)
        self.score_views.addWidget(self.midi_staff)
        layout.addWidget(self.score_views, 1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("MIDI track:"))
        self.track = QComboBox()
        controls.addWidget(self.track, 1)
        self.first = QSpinBox(); self.first.setMinimum(1)
        self.last = QSpinBox(); self.last.setMinimum(1)
        self.first.setKeyboardTracking(False)
        self.last.setKeyboardTracking(False)
        controls.addWidget(QLabel("From bar:")); controls.addWidget(self.first)
        controls.addWidget(QLabel("To bar:")); controls.addWidget(self.last)
        self.loop_current = QCheckBox("Loop current passage")
        self.loop_current.setChecked(database.get_setting("reading_loop_current", "0") == "1")
        self._saved_loop = self.loop_current.isChecked()
        self.loop_current.toggled.connect(self._loop_changed)
        controls.addWidget(self.loop_current)
        self.start = QPushButton("Start / restart slow practice")
        self.start.clicked.connect(self.start_practice)
        controls.addWidget(self.start)
        layout.addLayout(controls)
        self.target = QLabel()
        self.target.setWordWrap(True)
        self.target.setStyleSheet("font-size: 17px; font-weight: 600")
        layout.addWidget(self.target)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.keyboard = PianoKeyboard(36, 96)
        self.keyboard.setMinimumHeight(95)
        self.keyboard.setMaximumHeight(120)
        self.keyboard.note_changed.connect(controller.demo_note)
        layout.addWidget(self.keyboard)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.save = QPushButton("Retry saving this completed lesson")
        self.save.clicked.connect(self._save_result)
        self.save.hide()
        layout.addWidget(self.save)
        self.track.currentIndexChanged.connect(self._track_changed)
        for spin in (self.first, self.last):
            spin.valueChanged.connect(self._range_changed)
        controller.event_received.connect(self._event)
        controller.notes_changed.connect(self._notes)

    def open_score(self, source, folder):
        summary = load_midi(folder / "score.mid")
        if not summary.notes or len(summary.notes) > 100_000:
            raise ValueError("The downloaded MIDI is empty or too large for interactive practice")
        self._running = False
        self._repeat_pending = False
        self.follower = None
        self.source, self.summary = source, summary
        self.lesson = None
        self.document.close()
        self._all_score = load_falling_midi(folder / "score.mid")[0]
        self.midi_staff.set_score(self._all_score)
        if (folder / "score.pdf").is_file():
            error = self.document.load(str(folder / "score.pdf"))
            if error != QPdfDocument.Error.None_:
                raise ValueError("The downloaded PDF could not be opened")
            self.score_mode.setCurrentIndex(1)
        else:
            self.score_mode.setCurrentIndex(0)
        self._view_changed()
        self.folder = folder
        self.falling_button.setEnabled(True)
        self._update_title()
        self.track.blockSignals(True)
        self.track.clear()
        self.track.addItem("All pitched tracks", -1)
        for index in sorted({note.track for note in summary.notes if note.channel != 9}):
            count = sum(note.track == index for note in summary.notes)
            self.track.addItem(f"Track {index + 1} ({count} notes)", index)
        self.track.blockSignals(False)
        self.track.setEnabled(True)
        self._track_changed()
        self.score_opened.emit((source, folder))

    def open_lesson(self, lesson):
        self._running = self._repeat_pending = False
        self.follower = self.summary = self.source = self.folder = None
        self.lesson = lesson
        self.document.close()
        self._all_score = score_from_lesson(lesson)
        with QSignalBlocker(self.track):
            self.track.clear()
            self.track.addItem("All pitched tracks", -1)
        self.track.setEnabled(False)
        self.score_mode.setCurrentIndex(0)
        self._view_changed()
        self._update_title()
        self._track_changed()
        self.score_opened.emit((lesson, None))

    def _open_falling(self):
        if self.lesson:
            self.lesson_falling_requested.emit((self.lesson, self.first.value(), self.last.value(), *self.hands.values()))
        else:
            self.falling_requested.emit((self.source, self.folder, self.track.currentData(),
                                         self.first.value(), self.last.value(), "bar", *self.hands.values()))

    def _view_changed(self):
        has_pdf = self.document.pageCount() > 0
        original = has_pdf and self.score_mode.currentIndex() == 1
        self.score_mode.setEnabled(has_pdf)
        self.notation_controls.setEnabled(not original)
        self.score_views.setCurrentWidget(self.pdf if original else self.midi_staff)
        self.explanation.setText("Read the original PDF; MIDI supplies the note order. Turn PDF pages yourself. This is pitch practice, not rhythm or fingering assessment." if original else
            "Full MIDI practice score: scroll through the whole song, or follow highlighted bars while playing. Zoom and bars per line are saved. Not a reconstruction of the original edition.")
        if self.follower:
            self._target()

    def _update_title(self):
        self.title.setText(tr(self.lesson.title) if self.lesson else
                          self.source.title + " · " + self.source.composer + " · " + tr(self.source.license)
                          if self.source else tr("Choose a score to begin."))

    def _track_changed(self, *, preserve_range=False):
        if self._all_score is None:
            return
        first, last = self.first.value(), self.last.value()
        track = self.track.currentData()
        self.full_score = self.hands.apply(self._all_score, track)
        self.groups = self.full_score.groups
        self.midi_staff.set_score(self.full_score)
        total = len(self.full_score.timeline.measures)
        with QSignalBlocker(self.first), QSignalBlocker(self.last):
            self.first.setRange(1, total)
            self.last.setRange(1, total)
            self.first.setValue(first if preserve_range else 1)
            self.last.setValue(last if preserve_range else min(4, total))
        self._range_changed()

    def _hand_changed(self):
        self._track_changed(preserve_range=True)

    def _range_changed(self):
        self._running = False
        self._repeat_pending = False
        self.follower = None
        self._section = None
        self._saved = False
        self.save.hide()
        self.progress_bar.setValue(0)
        self.keyboard.set_expected_notes(frozenset())
        self.target.clear()
        valid = self.full_score is not None and self.first.value() <= self.last.value()
        self.start.setEnabled(False)
        self.falling_button.setEnabled(valid)
        if not valid:
            self.feedback.setText("The first bar must not be after the last bar. Adjust either field; the other value is kept.")
            return
        self._section, self._offset = self.full_score.measure_section(self.first.value(), self.last.value())
        self.start.setEnabled(bool(self._section.groups))
        self.feedback.setText("Choose start and end bars, read the score, then start slow practice. Both fields are independent." if self._section.groups else
                              "Rest-only passage. Read and count the beats; no grade is recorded and automatic looping stays stopped.")
        self.target.setText(f"Bars: {self.first.value()}–{self.last.value()} / {len(self.full_score.timeline.measures)} · Note groups: {len(self._section.groups)}")
        self.midi_staff.set_position(self._offset, force_follow=True)

    def save_loop_option(self):
        value = self.loop_current.isChecked()
        if value == self._saved_loop:
            return
        try:
            self.database.set_setting("reading_loop_current", "1" if value else "0")
            self._saved_loop = value
        except sqlite3.Error:
            self.feedback.setText("Loop choice could not be saved. It still applies now; leaving or closing will retry.")

    def _loop_changed(self):
        self._repeat_pending = bool(self._active and self.loop_current.isChecked() and self._saved
                                    and self.follower and self.follower.finished)
        self._maybe_repeat()
        self.save_loop_option()

    def _maybe_repeat(self):
        if not self._repeat_pending or not self._active or not self.loop_current.isChecked():
            return
        if self.controller.pressed_notes:
            self.feedback.setText("Passage complete. Release all keys to repeat these bars.")
            return
        self.start_practice()

    def showEvent(self, event):
        super().showEvent(event)
        self._active = True

    def hideEvent(self, event):
        self.hands.save_options()
        self.notation_controls.save_options()
        self.save_loop_option()
        self._repeat_pending = False
        self._active = False
        self._running = False
        super().hideEvent(event)

    def start_practice(self):
        self._repeat_pending = False
        if self.full_score is None:
            self.feedback.setText("Download a score from the online library to begin.")
            return
        if self.controller.pressed_notes:
            self.feedback.setText("Release or clear all keys first.")
            return
        if self.first.value() > self.last.value():
            self.feedback.setText("The first bar must not be after the last bar. Adjust either field; the other value is kept.")
            return
        if self._section is None or not self._section.groups:
            self.feedback.setText("Rest-only passage. Read and count the beats; no grade is recorded and automatic looping stays stopped.")
            return
        self.follower = MidiScoreFollower(self._section.groups)
        self._running, self._saved = True, False
        self._started = time.monotonic()
        self.save.hide()
        self.progress_bar.setRange(0, len(self.follower.groups))
        self.progress_bar.setValue(0)
        self.feedback.setText("Play fresh note attacks at your own pace. Previous notes may stay held; repeated notes need a new key press.")
        self._target()

    def _target(self):
        self.keyboard.set_expected_notes(self.follower.expected)
        if self.score_views.currentWidget() is self.midi_staff:
            group = self.follower.groups[min(self.follower.index, len(self.follower.groups) - 1)]
            seconds = self._offset + (max(0, self._section.duration - 1e-7) if self.follower.finished else group.time)
            self.midi_staff.set_position(seconds)
        if self.follower.finished:
            self.target.setText("Selected passage complete.")
            return
        bar = self.full_score.timeline.measure_index(self._offset + self.follower.groups[self.follower.index].time) + 1
        notes = self.follower.expected
        if notes and (min(notes) < self.keyboard.start_note or max(notes) >= self.keyboard.end_note):
            self.keyboard.start_note = max(0, (min(notes) // 12 - 1) * 12)
            self.keyboard.end_note = min(128, max(self.keyboard.start_note + 36, (max(notes) // 12 + 1) * 12))
        names = " ".join(midi_note_name(note) for note in sorted(self.follower.expected))
        self.target.setText(f"{tr('Bar')} {bar} / {self.last.value()} · {tr('Group')} {self.follower.index + 1} / {len(self.follower.groups)} · {tr('New notes:')} {names}")

    def _notes(self, notes):
        if self._active:
            self.keyboard.set_notes(notes)

    def _event(self, payload):
        if not self._active:
            return
        if not self._running:
            self._maybe_repeat()
            return
        event = payload["event"]
        result = self.follower.event(event)
        self.progress_bar.setValue(self.follower.index)
        if result == "extra":
            self.feedback.setText(f"Extra note: {midi_note_name(event.note)}. Correct it and continue.")
        elif result == "advanced":
            self.feedback.setText("Correct. Continue with the next group.")
        elif result == "finished":
            self._running = False
            self._save_result()
        self._target()

    def _save_result(self):
        if self.follower is None or not self.follower.finished or self._saved:
            return
        try:
            key = "builtin:" + self.lesson.id if self.lesson else f"{self.source.provider}:{self.source.id}"
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="downloaded_score", skill="score_playing",
                question=f"{key}:track:{self.track.currentData()}:bars:{self.first.value()}-{self.last.value()}" + self.hands.question_suffix(),
                expected=str([sorted(group.notes) for group in self.follower.groups]), played="Completed MIDI note groups",
                correct=self.follower.mistakes == 0, response_time_ms=max(0, round((time.monotonic() - self._started) * 1000)),
                metadata={"source_url": self.source.source_url if self.source else "", "license": self.source.license if self.source else "Built-in teaching score",
                          "completed": True, "corrected_notes": self.follower.mistakes, "timing_graded": False,
                          "range_unit": "bar", "first_bar": self.first.value(), "last_bar": self.last.value(), **self.hands.metadata()},
            )
        except sqlite3.Error as exc:
            self.save.show()
            QMessageBox.critical(self, "Database error", str(exc))
            return
        self._saved = True
        self.save.hide()
        self.feedback.setText(f"Completed! Notes corrected: {self.follower.mistakes}. You may repeat or choose another passage.")
        self.attempt_recorded.emit()
        self._repeat_pending = self.loop_current.isChecked()
        self._maybe_repeat()
