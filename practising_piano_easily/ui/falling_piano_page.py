"""Separate falling-piano workspace using existing lessons, PDFs, MIDI and progress storage."""

from bisect import bisect_right
from html import escape
import math
import sqlite3
import time
from urllib.parse import quote, unquote

from PySide6.QtCore import Signal, QSignalBlocker, QTimer, Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QScrollArea, QFrame,
                               QStackedWidget, QSpinBox, QProgressBar, QComboBox as SourceCombo, QLabel as PlainLabel)

from practising_piano_easily.analysis.falling_score import load_falling_midi
from practising_piano_easily.analysis.score_harmony import harmony_at
from practising_piano_easily.audio.score_demo import ScoreDemoPlayer
from practising_piano_easily.chord_learning import quality_label
from practising_piano_easily.core import parse_chord
from practising_piano_easily.analysis.online_scores import downloaded_scores, score_folder, SOURCE_NAMES
from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES
from practising_piano_easily.trainers.falling_notes import FallingSession, score_from_lesson
from practising_piano_easily.trainers.chord_construction import midi_note_name
from .localized_widgets import QLabel, QPushButton, QComboBox, QCheckBox, QMessageBox
from .keyboard_widget import PianoKeyboard
from .falling_notes_widget import FallingNotesWidget
from .midi_notation_widget import MidiNotationWidget
from .notation_controls import NotationControls
from .hand_controls import HandControls
from .pdf_score_position import first_staff_top
from .i18n import language, tr


class FallingPianoPage(QWidget):
    attempt_recorded = Signal()
    chord_requested = Signal(str)

    def __init__(self, controller, database, session_id):
        super().__init__()
        self.controller, self.database, self.session_id = controller, database, session_id
        self._active = False
        self._entries = {}
        self._added_sources = {}
        self._restore_key = database.get_setting("falling_last_song")
        self._last_saved_key = self._restore_key
        self._loaded_key = None
        self.demo_player = ScoreDemoPlayer()
        self._lesson = None
        self.source_info = None
        self.full_score = self._all_score = None
        self.session = None
        self._offset = 0.0
        self._pdf_start_y = 0.0
        self._harmony_key = None
        self._chord_text = ""
        self._saved = False
        self._good_held, self._wrong_held = set(), set()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self._resume_deadline = None
        self._next_deadline = None
        self._repeat_requested = False
        self._demo_practice = None
        self._section_demo = False
        self._section_demonstrated = False
        self.next_timer = QTimer(self)
        self.next_timer.setInterval(100)
        self.next_timer.timeout.connect(self._next_tick)
        self.resume_timer = QTimer(self)
        self.resume_timer.setInterval(100)
        self.resume_timer.timeout.connect(self._resume_tick)
        layout = QVBoxLayout(self)
        heading = QLabel("Falling piano")
        heading.setStyleSheet("font-size: 24px; font-weight: 700")
        heading_row = QHBoxLayout()
        heading_row.addWidget(heading)
        heading_row.addStretch()
        self.demo_before = QCheckBox("Demonstrate before practice")
        self.demo_before.setChecked(database.get_setting("falling_demo_before", "0") == "1")
        self.demo_before.toggled.connect(self._demo_before_changed)
        heading_row.addWidget(self.demo_before)
        self.loop_current = QCheckBox("Loop current passage · default four bars")
        self.loop_current.setChecked(database.get_setting("falling_loop_current", "0") == "1")
        self._saved_practice_options = (self.demo_before.isChecked(), self.loop_current.isChecked())
        self.loop_current.setToolTip(tr("Repeat this selected passage. Demonstration follows its own switch; use Next passage when ready."))
        self.loop_current.toggled.connect(self._loop_changed)
        heading_row.addWidget(self.loop_current)
        self.next_button = QPushButton("Next passage")
        self.next_button.clicked.connect(self.next_passage)
        heading_row.addWidget(self.next_button)
        layout.addLayout(heading_row)
        first_row = QHBoxLayout()
        self.source_picker = SourceCombo()
        self.source_picker.setSizeAdjustPolicy(SourceCombo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source_picker.setMinimumContentsLength(18)
        first_row.addWidget(QLabel("Score:"))
        first_row.addWidget(self.source_picker, 1)
        refresh = QPushButton("Refresh library")
        refresh.clicked.connect(self.refresh_sources)
        first_row.addWidget(refresh)
        self.score_mode = QComboBox()
        self.score_mode.addItems(["Synchronized practice score", "Original PDF"])
        first_row.addWidget(self.score_mode)
        self.mode = QComboBox()
        self.mode.addItems(["Follow · wait for me", "Preview · visual only", "Demo · watch and listen"])
        first_row.addWidget(self.mode)
        layout.addLayout(first_row)
        second_row = QHBoxLayout()
        self.track = QComboBox()
        self.track.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.track.setMinimumContentsLength(8)
        second_row.addWidget(QLabel("MIDI track:"))
        second_row.addWidget(self.track, 1)
        self.range_mode = QComboBox()
        self.range_mode.addItems(["Measure practice", "Note-group passage"])
        second_row.addWidget(self.range_mode)
        self.first, self.last = QSpinBox(), QSpinBox()
        self.first_label, self.last_label = QLabel(), QLabel()
        for label, spin in ((self.first_label, self.first), (self.last_label, self.last)):
            spin.setMinimum(1)
            spin.setKeyboardTracking(False)
            second_row.addWidget(label)
            second_row.addWidget(spin)
        self.speed = QSpinBox()
        self.speed.setRange(25, 200)
        self.speed.setValue(100)
        self.speed.setSuffix(" %")
        second_row.addWidget(QLabel("Speed:")); second_row.addWidget(self.speed)
        self.lookahead = QSpinBox()
        self.lookahead.setRange(3, 10)
        self.lookahead.setValue(4)
        self.lookahead.setSuffix(" s")
        second_row.addWidget(QLabel("Look ahead:")); second_row.addWidget(self.lookahead)
        layout.addLayout(second_row)
        transport = QHBoxLayout()
        self.play_button = QPushButton("Start / resume")
        self.play_button.clicked.connect(self.start)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause)
        self.restart_button = QPushButton("Restart")
        self.restart_button.clicked.connect(self.restart)
        for button in (self.play_button, self.pause_button, self.restart_button):
            transport.addWidget(button)
        self.demo_button = QPushButton("Demonstrate full song")
        self.demo_button.clicked.connect(self.demonstrate)
        transport.addWidget(self.demo_button)
        self.key_range = QComboBox()
        self.key_range.addItems(["Fit keys to score", "Show all 88 keys"])
        self.key_range.currentIndexChanged.connect(self._keyboard_range)
        transport.addWidget(self.key_range)
        self.auto_pdf = QCheckBox("Auto-scroll PDF · estimated, not note-aligned")
        self.auto_pdf.setChecked(True)
        transport.addWidget(self.auto_pdf)
        transport.addStretch()
        layout.addLayout(transport)
        self.hands = HandControls(database, "falling")
        self.hands.changed.connect(self._hand_changed)
        layout.addWidget(self.hands)
        self.score_hint = QLabel()
        self.score_hint.setWordWrap(True)
        layout.addWidget(self.score_hint)
        self.credit = PlainLabel()
        self.credit.setTextFormat(Qt.TextFormat.PlainText)
        self.credit.setWordWrap(True)
        layout.addWidget(self.credit)
        self.harmony_scroll = QScrollArea()
        self.harmony_scroll.setWidgetResizable(True)
        self.harmony_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.harmony_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Reserve the same space for rests and multi-candidate chords so notation never reflows mid-line.
        self.harmony_scroll.setFixedHeight(96)
        harmony = QWidget()
        harmony_layout = QVBoxLayout(harmony)
        harmony_layout.setContentsMargins(0, 0, 0, 0)
        harmony_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.harmony_scroll.setWidget(harmony)
        layout.addWidget(self.harmony_scroll)
        self.chord_label = PlainLabel()
        self.chord_label.setTextFormat(Qt.TextFormat.RichText)
        self.chord_label.setOpenExternalLinks(False)
        self.chord_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.chord_label.linkActivated.connect(self._open_chord_link)
        self.chord_label.setWordWrap(True)
        self.chord_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #1d4ed8")
        harmony_layout.addWidget(self.chord_label)
        self.chord_tones = PlainLabel()
        self.chord_tones.setTextFormat(Qt.TextFormat.PlainText)
        self.chord_tones.setWordWrap(True)
        harmony_layout.addWidget(self.chord_tones)
        self.chord_keys = PlainLabel()
        self.chord_keys.setTextFormat(Qt.TextFormat.PlainText)
        self.chord_keys.setWordWrap(True)
        harmony_layout.addWidget(self.chord_keys)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.score_views = QStackedWidget()
        self.document = QPdfDocument(self)
        self.pdf = QPdfView(self)
        self.pdf.setDocument(self.document)
        self.pdf.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.pdf.verticalScrollBar().rangeChanged.connect(self._render)
        self.score_views.addWidget(self.pdf)
        self.midi_staff = MidiNotationWidget()
        self.notation_controls = NotationControls(self.midi_staff, database, "falling_notation")
        layout.insertWidget(layout.indexOf(self.score_hint), self.notation_controls)
        self.score_views.addWidget(self.midi_staff)
        self.score_mode.currentIndexChanged.connect(self._view_changed)
        self.score_views.setMinimumHeight(self.midi_staff.minimumHeight())
        self.splitter.addWidget(self.score_views)
        lower = QWidget()
        lower.setMinimumHeight(260)
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(0)
        self.keyboard = PianoKeyboard(36, 84)
        self.keyboard.label_all_notes = True
        self.keyboard.setMinimumHeight(110)
        self.keyboard.setMaximumHeight(130)
        self.keyboard.note_changed.connect(controller.demo_note)
        self.roll = FallingNotesWidget(self.keyboard)
        self.resume_notice = QLabel("", self.roll)
        self.resume_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resume_notice.setWordWrap(True)
        self.resume_notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resume_notice.setStyleSheet("background-color: rgba(15, 23, 42, 230); color: #fbbf24; font-size: 28px; padding: 12px; border-radius: 12px")
        self.resume_notice.hide()
        lower_layout.addWidget(self.roll, 1)
        lower_layout.addWidget(self.keyboard)
        self.splitter.addWidget(lower)
        self.splitter.setSizes([340, 360])
        layout.addWidget(self.splitter, 1)
        self.feedback = QLabel("Choose a score. Blocks reach the yellow line when it is time to press the keys.")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        layout.addWidget(self.progress)
        self.save_button = QPushButton("Retry saving this completed lesson")
        self.save_button.clicked.connect(self._save_result)
        self.save_button.hide()
        layout.addWidget(self.save_button)
        self.source_picker.currentIndexChanged.connect(self._select_source)
        self.track.currentIndexChanged.connect(self._track_changed)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.range_mode.currentIndexChanged.connect(self._range_changed)
        self.first.valueChanged.connect(self._make_session)
        self.last.valueChanged.connect(self._make_session)
        self.lookahead.valueChanged.connect(lambda: self._render())
        controller.event_received.connect(self._event)
        controller.notes_changed.connect(self._notes)
        language.changed.connect(self._retranslate_sources)
        self.refresh_sources()

    def refresh_sources(self):
        key = self.source_picker.currentData()
        restore = key is None and self._restore_key is not None
        if restore:
            key = self._restore_key
            self._restore_key = None
        previous = self._entries.get(key)
        entries = {"builtin:" + lesson.id: (lesson, None) for lesson in LESSONS + PIECES}
        entries.update({f"{score.provider}:{score.id}": (score, score_folder(score)) for score in downloaded_scores()})
        entries.update(self._added_sources)
        if key not in entries and previous:
            entries[key] = previous
        self._entries = entries
        with QSignalBlocker(self.source_picker):
            self.source_picker.clear()
            for item_key, (item, folder) in entries.items():
                self.source_picker.addItem(self._source_title(item, folder), item_key)
            self.source_picker.setCurrentIndex(max(0, self.source_picker.findData(key)))
        if key != self.source_picker.currentData() or self.session is None:
            self._select_source()
        if restore and self.session is None:
            # A deleted or damaged last download must not leave the entry page unusable.
            self.source_picker.setCurrentIndex(0)

    def add_downloaded(self, payload):
        score, folder = payload
        key = f"{score.provider}:{score.id}"
        self._added_sources[key] = self._entries[key] = (score, folder)
        with QSignalBlocker(self.source_picker):
            index = self.source_picker.findData(key)
            if index < 0:
                self.source_picker.addItem(self._source_title(score, folder), key)
            else:
                self.source_picker.setItemText(index, self._source_title(score, folder))

    def save_last_song(self):
        key = self.source_picker.currentData()
        if self.session is None or self._loaded_key != key or key == self._last_saved_key:
            return
        try:
            self.database.set_setting("falling_last_song", key)
            self._last_saved_key = key
        except sqlite3.Error:
            self.feedback.setText("Last song could not be saved. Your practice records are unchanged.")

    def save_practice_options(self):
        values = (self.demo_before.isChecked(), self.loop_current.isChecked())
        if values == self._saved_practice_options:
            return
        try:
            self.database.set_settings({"falling_demo_before": "1" if values[0] else "0",
                                        "falling_loop_current": "1" if values[1] else "0"})
            self._saved_practice_options = values
        except sqlite3.Error:
            self.feedback.setText("Practice switches could not be saved. They still apply now; saving will be retried when leaving.")

    def _source_title(self, item, folder):
        prefix = tr(SOURCE_NAMES[item.provider]) if folder else tr("Course" if item in LESSONS else "Repertoire")
        return prefix + " · " + (item.title if folder else tr(item.title))

    def _retranslate_sources(self):
        with QSignalBlocker(self.source_picker):
            for index in range(self.source_picker.count()):
                item, folder = self._entries[self.source_picker.itemData(index)]
                self.source_picker.setItemText(index, self._source_title(item, folder))
        self._update_credit()
        self._render()

    def open_lesson(self, lesson):
        self.refresh_sources()
        index = self.source_picker.findData("builtin:" + lesson.id)
        if index == self.source_picker.currentIndex():
            self._select_source()
        else:
            self.source_picker.setCurrentIndex(index)

    def open_downloaded(self, payload):
        score, folder, track, first, last = payload[:5]
        by_bar = len(payload) > 5 and payload[5] == "bar"
        key = f"{score.provider}:{score.id}"
        self.refresh_sources()
        self.add_downloaded((score, folder))
        index = self.source_picker.findData(key)
        if index == self.source_picker.currentIndex():
            self._select_source()
        else:
            self.source_picker.setCurrentIndex(index)
        if self.session:
            if len(payload) > 6:
                hand, split = payload[6:8]
                with QSignalBlocker(self.hands.hand), QSignalBlocker(self.hands.split):
                    self.hands.hand.setCurrentIndex(max(0, self.hands.hand.findData(hand)))
                    self.hands.split.setValue(split)
                self.hands.save_options()
            with QSignalBlocker(self.range_mode):
                self.range_mode.setCurrentIndex(0 if by_bar else 1)
            self.track.setCurrentIndex(max(0, self.track.findData(track)))
            self._track_changed()
            with QSignalBlocker(self.first), QSignalBlocker(self.last):
                self.first.setValue(first)
                self.last.setValue(last)
            self._make_session()

    def _select_source(self):
        self.pause()
        self.session = None
        self._loaded_key = None
        self.full_score = None
        self._all_score = None
        self.roll.session = None
        self._lesson = self.source_info = None
        self._demo_practice = None
        with QSignalBlocker(self.range_mode):
            self.range_mode.setCurrentIndex(0)
        self.chord_label.clear()
        self.chord_tones.clear()
        self.chord_keys.clear()
        self.keyboard.set_reference_notes(frozenset())
        self._harmony_key = None
        with QSignalBlocker(self.score_mode):
            self.score_mode.setCurrentIndex(0)
        item, folder = self._entries[self.source_picker.currentData()]
        try:
            self.document.close()
            with QSignalBlocker(self.track):
                self.track.clear()
                self.track.addItem("All pitched tracks", -1)
                if folder is None:
                    self._lesson = item
                    self._all_score = score_from_lesson(item)
                else:
                    self.source_info = item
                    self._all_score, summary = load_falling_midi(folder / "score.mid")
                    for index in sorted({note.track for note in summary.notes if note.channel != 9}):
                        self.track.addItem(f"Track {index + 1}", index)
                    if (folder / "score.pdf").is_file():
                        if self.document.load(str(folder / "score.pdf")) != QPdfDocument.Error.None_:
                            raise ValueError("The downloaded PDF could not be opened")
                        self._pdf_start_y = first_staff_top(self.document)
                        QTimer.singleShot(0, self._reset_pdf_position)
            self._view_changed()
            self._update_credit()
            self._track_changed()
            if self.session is not None:
                self._loaded_key = self.source_picker.currentData()
        except (ValueError, OSError) as exc:
            self.feedback.setText(str(exc))
            self.play_button.setEnabled(False)
            self.restart_button.setEnabled(False)
            self.demo_button.setEnabled(False)
            self._update_loop_controls()
            self.roll.update()

    def _update_credit(self):
        self.credit.setText(self.source_info.title + " · " + self.source_info.composer + " · " + tr(self.source_info.license)
                            if self.source_info else "")
        self.credit.setVisible(self.source_info is not None)

    def _view_changed(self):
        has_pdf = self.source_info is not None and self.document.pageCount() > 0
        original = has_pdf and self.score_mode.currentIndex() == 1
        self.score_mode.setEnabled(has_pdf)
        self.notation_controls.setEnabled(not original)
        self.score_mode.setToolTip("" if has_pdf else tr("No PDF attached; using the MIDI practice score."))
        self.auto_pdf.setVisible(original)
        self.score_views.setCurrentWidget(self.pdf if original else self.midi_staff)
        self.score_hint.setText("Built-in score: two stable staff systems, advancing by line. Blue = right hand; teal = left hand." if self._lesson else
            "PDF scrolling is estimated from progress, not exact note tracking. You can turn it off and scroll manually. MIDI colors represent tracks, not hands." if original else
            "MIDI-only score: two stable staff systems, advancing by line with the blocks. No original PDF is attached." if not has_pdf else
            "Practice score: two stable staff systems, advancing by line; the current bar stays highlighted. Rhythm glyphs are approximate, not original notation. Original PDF is available above.")
        self._render()

    def _track_changed(self, *, preserve_range=False):
        self.pause()
        if self._all_score is None:
            return
        first, last = self.first.value(), self.last.value()
        track = self.track.currentData()
        try:
            self.full_score = self.hands.apply(self._all_score, track)
            self.midi_staff.set_score(self.full_score)
        except ValueError as exc:
            self.session = None
            self.feedback.setText(str(exc))
            self.play_button.setEnabled(False)
            self._update_loop_controls()
            return
        self._range_changed()
        if preserve_range:
            self._set_bar_range(first, last)

    def _hand_changed(self):
        self._track_changed(preserve_range=True)

    def _range_changed(self):
        self.pause()
        if self.full_score is None:
            return
        by_bar = self.range_mode.currentIndex() == 0
        total = len(self.full_score.timeline.measures) if by_bar else len(self.full_score.groups)
        self.first_label.setText("From bar:" if by_bar else "From group:")
        self.last_label.setText("To bar:" if by_bar else "To group:")
        with QSignalBlocker(self.first), QSignalBlocker(self.last):
            self.first.setRange(1, total)
            self.last.setRange(1, total)
            self.first.setValue(1)
            self.last.setValue(min(4, total) if by_bar else total)
        self._make_session()

    def _practice_bars(self):
        if self.range_mode.currentIndex() == 0:
            first, last = self.first.value(), self.last.value()
        elif not self.full_score.groups:
            first, last = 1, min(4, len(self.full_score.timeline.measures))
        else:
            first = self.full_score.timeline.measure_index(self.full_score.groups[self.first.value() - 1].time) + 1
            last = min(len(self.full_score.timeline.measures), first + 3)
        return self.track.currentData(), first, last

    def _mode_changed(self):
        if self.mode.currentIndex() == 2 and self.full_score is not None:
            self._demo_practice = self._practice_bars()
        self._make_session()

    def _make_session(self):
        self.pause()
        self._section_demo = self._section_demonstrated = False
        self.roll.session = None
        if self.full_score is None:
            return
        try:
            if self.range_mode.currentIndex() == 0:
                if self.first.value() > self.last.value():
                    raise ValueError("The first bar must not be after the last bar. Adjust either field; the other value is kept.")
                score, self._offset = self.full_score.measure_section(self.first.value(), self.last.value())
            elif self.mode.currentIndex() == 2 and self.first.value() == 1 and self.last.value() == len(self.full_score.groups):
                score, self._offset = self.full_score, 0.0
            else:
                score, self._offset = self.full_score.section(self.first.value(), self.last.value())
            self.session = FallingSession(score, preview=self.mode.currentIndex() != 0)
        except ValueError as exc:
            self.session = None
            self.feedback.setText(str(exc))
            self.play_button.setEnabled(False)
            self.restart_button.setEnabled(False)
            self.demo_button.setEnabled(False)
            self._update_loop_controls()
            self.roll.update()
            return
        self._saved = False
        self._harmony_key = None
        self._good_held.clear(); self._wrong_held.clear()
        self.save_button.hide()
        self.roll.session = self.session
        self.play_button.setEnabled(True)
        self.restart_button.setEnabled(True)
        self.demo_button.setEnabled(True)
        self.feedback.setText("Rest-only passage. Count the beats; no keys are required and no grade is recorded." if not score.notes else
                              "Demo plays synthesized notes and lights the keys. It does not record practice." if self.mode.currentIndex() == 2 else
                              "Preview is visual only and does not record practice. Your MIDI keyboard supplies its own sound." if self.session.preview else
                              "Start: watch this passage first, then follow after a three-second countdown." if self.range_mode.currentIndex() == 0 and self.demo_before.isChecked() else
                              "Start, watch the blocks, and press at the yellow line. The timeline waits for correct notes; duration and rhythm are not graded.")
        self._keyboard_range()
        self._render()
        self._update_loop_controls()

    def _keyboard_range(self):
        if self.session is None:
            return
        pitches = [note.pitch for note in (self.session.score.notes or self.full_score.notes or self._all_score.notes)]
        if self.key_range.currentIndex() == 1:
            start, end = min(21, min(pitches) // 12 * 12), max(109, max(pitches) + 1)
        else:
            start, end = max(0, min(pitches) // 12 * 12 - 12), min(128, (max(pitches) // 12 + 2) * 12)
            if end - start < 36:
                start = max(0, start - 12)
        self.keyboard.start_note, self.keyboard.end_note = start, end
        self.keyboard.update()
        self.roll.update()
        self._render()

    def _set_running(self, running):
        for widget in (self.source_picker, self.track, self.range_mode, self.first, self.last, self.mode, self.hands):
            widget.setEnabled(not running)
        self.track.setEnabled(not running and self.source_info is not None)
        self.play_button.setEnabled(not running and self.session is not None)
        self.pause_button.setEnabled(running)
        self._update_loop_controls()

    def _update_loop_controls(self):
        by_bar = self.session is not None and self.range_mode.currentIndex() == 0 and self.mode.currentIndex() == 0
        unsaved = bool(self.session and self.session.finished and not self.session.preview
                       and self.session.score.groups and not self._saved)
        self.loop_current.setEnabled(by_bar)
        self.demo_before.setEnabled(by_bar)
        self.next_button.setEnabled(by_bar and self.last.value() < self.last.maximum() and not unsaved)

    def _demo_before_changed(self):
        if self._section_demo and not self.demo_before.isChecked():
            running = self.session.running
            self._section_demo_finished(resume=running)
            self.feedback.setText("Demo skipped. Follow after the countdown." if running else "Demo disabled. Start to follow.")
        elif self.session and not self._section_demonstrated and not self.session.preview and not self.session.finished:
            self.feedback.setText("Start: watch this passage first, then follow after a three-second countdown." if self.demo_before.isChecked() else
                                  "Start, watch the blocks, and press at the yellow line. The timeline waits for correct notes; duration and rhythm are not graded.")
        self.save_practice_options()

    def _loop_changed(self):
        if self._next_deadline is not None:
            requested = self._repeat_requested
            self.pause()
            self._queue_next_measures(repeat_requested=requested)
        self.save_practice_options()

    def next_passage(self):
        self._update_loop_controls()
        if not self._active or not self.next_button.isEnabled():
            return
        first = self.last.value() + 1
        last = min(self.last.maximum(), first + self.last.value() - self.first.value())
        self._start_bar_range(first, last)

    def _start_bar_range(self, first, last):
        self._set_bar_range(first, last)
        self.session.position = 0
        self._render()
        self.start()

    def start(self):
        self.pause()
        if not self._active or self.session is None:
            return
        if self.session.finished:
            self._make_session()
        if self.mode.currentIndex() == 0 and self.range_mode.currentIndex() == 0 and not self._section_demonstrated:
            if self.demo_before.isChecked():
                self._section_demo = True
                self.session.preview = True
        if self.controller.pressed_notes and not self.session.preview:
            self.feedback.setText("Release or clear all keys first.")
            return
        if self.mode.currentIndex() == 0 and self.range_mode.currentIndex() == 0 and not self._section_demo:
            self._section_demonstrated = True
        self.session.follower.held.clear()
        self._good_held.clear(); self._wrong_held.clear()
        self.session.running = True
        self.session.speed = self.speed.value() / 100
        if self._is_demonstrating():
            message = (f"{tr('Passage demo: bars')} {self.first.value()}–{self.last.value()} · " + tr("Watch first; follow after the countdown.")
                       if self._section_demo else tr("Demo plays synthesized notes and lights the keys. It does not record practice."))
            try:
                device = self.database.get_setting("audio_output", "")
                self.demo_player.start(self.session.score, self.session.position, self.session.speed,
                    int(self.database.get_setting("ear_volume", "25")) / 100, int(device) if device else None)
                self.feedback.setText(message)
            except Exception as exc:
                self.feedback.setText(message + " " + tr("Demo audio unavailable; continuing visually.") + " " + str(exc))
        self._clock = time.monotonic()
        self.timer.start()
        self._set_running(True)

    def _is_demonstrating(self):
        return self._section_demo or self.mode.currentIndex() == 2

    def _section_demo_finished(self, *, resume=True):
        self._make_session()
        self._section_demonstrated = True
        self.session.position = 0
        self._render()
        self.feedback.setText("Passage demo complete. Release the keys; follow after the countdown.")
        if resume:
            self.resume_after_countdown()

    def pause(self):
        self.next_timer.stop()
        self._next_deadline = None
        self._repeat_requested = False
        self.resume_timer.stop()
        self._resume_deadline = None
        self.resume_notice.hide()
        self.timer.stop()
        self._stop_demo()
        if self.session:
            self.session.running = False
        self._set_running(False)

    def _stop_demo(self):
        try:
            self.demo_player.stop()
        except Exception as exc:
            self.feedback.setText(tr("Demo audio unavailable; continuing visually.") + " " + str(exc))

    def demonstrate(self):
        self.pause()
        if self._all_score is None:
            return
        self._demo_practice = self._practice_bars()
        with QSignalBlocker(self.mode), QSignalBlocker(self.range_mode), QSignalBlocker(self.track):
            self.mode.setCurrentIndex(2)
            self.range_mode.setCurrentIndex(1)
            if self.hands.hand.currentData() == "both":
                self.track.setCurrentIndex(0)
        self._track_changed()
        self.start()

    def _demo_finished(self):
        track, first, last = self._demo_practice or (-1, 1, 4)
        with QSignalBlocker(self.mode), QSignalBlocker(self.range_mode), QSignalBlocker(self.track):
            self.mode.setCurrentIndex(0)
            self.range_mode.setCurrentIndex(0)
            self.track.setCurrentIndex(max(0, self.track.findData(track)))
        self._track_changed()
        self._set_bar_range(first, last)
        self.session.position = 0
        self._render()
        if self.demo_before.isChecked():
            self.start()
        else:
            self._section_demonstrated = True
            self.feedback.setText("Demo complete. Practice starts after the countdown; release all keys.")
            self.resume_after_countdown()

    def _set_bar_range(self, first, last):
        with QSignalBlocker(self.first), QSignalBlocker(self.last):
            self.first.setValue(first)
            self.last.setValue(last)
        self._make_session()

    def _queue_next_measures(self, *, repeat_requested=False):
        self._update_loop_controls()
        if (not self._active or self.range_mode.currentIndex() != 0 or self.mode.currentIndex() != 0
                or self.session is None or not self.session.finished or self.session.preview
                or (self.session.score.groups and not self._saved) or self._next_deadline is not None):
            return
        self._repeat_requested = repeat_requested
        self._next_deadline = time.monotonic() + 2
        self.pause_button.setEnabled(True)
        self.next_timer.start()
        self._next_tick()

    def _next_tick(self):
        if self._next_deadline is None:
            return
        if not self._active or self.session is None or not self.session.finished:
            self.pause()
            return
        now = time.monotonic()
        remaining = math.ceil(max(0, self._next_deadline - now))
        repeat = self.loop_current.isChecked() or self._repeat_requested
        at_end = self.last.value() >= self.last.maximum()
        first = self.first.value() if repeat else self.last.value() + 1
        last = self.last.value() if repeat else min(self.last.maximum(), first + self.last.value() - self.first.value())
        if remaining or self.controller.pressed_notes:
            target = tr("Finish or repeat") if at_end and not repeat else f"{tr('Repeat bars:' if repeat else 'Next bars:')} {first}–{last}"
            self._show_notice(f"{target} · {remaining}" if remaining else tr("Release keys to continue"))
            self.feedback.setText("Repeat requested. This passage restarts after the two-second window; release all keys first." if self._repeat_requested else
                                  "Loop enabled. This passage restarts after two seconds; release all keys first." if repeat else
                                  "Song complete. Press a key within two seconds to repeat; otherwise finish. Release all keys first." if at_end else
                                  "Passage complete. Press a key within two seconds to repeat; otherwise continue to the next bars. Release all keys first.")
            return
        if at_end and not repeat:
            self.pause()
            self.feedback.setText("Song practice complete. You can restart or choose another score.")
            return
        self._start_bar_range(first, last)

    def resume_after_countdown(self):
        self.pause()
        if not self._active or self.session is None or self.session.finished:
            return
        self._resume_deadline = time.monotonic() + 3
        self._set_running(True)
        self.resume_timer.start()
        self._resume_tick()

    def _resume_tick(self):
        if self._resume_deadline is None:
            return
        if not self._active or self.session is None or self.session.finished:
            self.pause()
            return
        remaining = math.ceil(max(0, self._resume_deadline - time.monotonic()))
        if not remaining and (self.session.preview or not self.controller.pressed_notes):
            self.start()
            return
        self._show_notice(f"{remaining} · {tr('Auto-resume')}" if remaining else tr("Release keys to resume"))

    def _show_notice(self, text):
        self.resume_notice.setGeometry(max(0, (self.roll.width() - 360) // 2), max(0, (self.roll.height() - 120) // 2), 360, 120)
        self.resume_notice.setText(text)
        self.resume_notice.show()
        self.resume_notice.raise_()

    def restart(self):
        self._make_session()
        self.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._active = True
        self.refresh_sources()
        self._render()

    def hideEvent(self, event):
        self.hands.save_options()
        self.notation_controls.save_options()
        self.save_practice_options()
        self.save_last_song()
        self._active = False
        self.pause()
        super().hideEvent(event)

    def _tick(self):
        if not self._active or self.session is None or not self.session.running:
            return
        now = time.monotonic()
        elapsed, self._clock = now - self._clock, now
        self.session.speed = self.speed.value() / 100
        if self.demo_player.stream is not None:
            try:
                self.demo_player.renderer.speed = self.session.speed
                elapsed = max(0, self.demo_player.position - self.session.position) / self.session.speed
            except Exception as exc:
                self._stop_demo()
                self.feedback.setText(tr("Demo audio unavailable; continuing visually.") + " " + str(exc))
        state = self.session.advance(elapsed)
        self._render()
        if state == "finished":
            self.timer.stop()
            self._stop_demo()
            self._set_running(False)
            if self._section_demo:
                self._section_demo_finished()
                return
            if self.mode.currentIndex() == 2:
                self._demo_finished()
                return
            self.feedback.setText("Preview complete · no practice recorded." if self.session.preview else "Passage complete. You can restart or choose another score.")
            self._save_result()
        elif state == "waiting":
            missing = " ".join(midi_note_name(note) for note in sorted(self.session.follower.expected))
            self.feedback.setText(f"Waiting at the line. Still needed: {missing}. You may correct the keys without rushing.")

    def _event(self, payload):
        if not self._active or self.session is None:
            return
        event = payload["event"]
        if (self._next_deadline is not None and time.monotonic() <= self._next_deadline
                and event.event_type == "note_on" and event.velocity > 0 and event.note is not None
                and event.note not in self.session.follower.held):
            self._repeat_requested = True
        state = self.session.event(event)
        if state == "released":
            self._good_held.discard(event.note)
            self._wrong_held.discard(event.note)
        elif state in {"waiting", "advanced", "finished"}:
            self._good_held.add(event.note)
            if state == "advanced":
                self.feedback.setText("Correct. Watch the next blocks.")
            elif state == "finished":
                self.feedback.setText("All notes matched. Let the final blocks finish.")
        elif state == "extra":
            self._wrong_held.add(event.note)
            self.feedback.setText(f"Release extra notes: {midi_note_name(event.note)}. You can keep the correct keys held.")
        elif state == "early":
            self.feedback.setText("Too early: release and press again when the block reaches the yellow line.")
        self._render()
        if self._next_deadline is not None:
            self._next_tick()

    def _notes(self, notes):
        if self._active:
            if self._is_demonstrating() and self.session:
                position = self.session.position
                notes = frozenset(note.pitch for note in self.session.score.visible_notes(position, 0)
                                  if note.start <= position < note.end)
                self.keyboard.set_notes(notes)
            else:
                self.keyboard.set_notes(notes, correct=frozenset(notes & self._good_held), incorrect=frozenset(notes & self._wrong_held))

    def _reset_pdf_position(self):
        if self.source_info and self.session:
            self._scroll_pdf(0)
            self._render()

    def _scroll_pdf(self, progress):
        bar = self.pdf.verticalScrollBar()
        margins = self.pdf.documentMargins()
        page_width = self.document.pagePointSize(0).width()
        if page_width <= 0:
            return
        scale = max(0, self.pdf.viewport().width() - margins.left() - margins.right()) / page_width
        start = min(bar.maximum(), margins.top() + self._pdf_start_y * scale)
        bar.setValue(round(start + min(1, max(0, progress)) * (bar.maximum() - start)))

    def _render(self):
        if self.session is None:
            return
        session = self.session
        self.roll.lookahead = self.lookahead.value()
        self.roll.update()
        target = session.follower.expected if not session.preview and session.waiting else frozenset()
        self.keyboard.set_expected_notes(target)
        self._notes(self.controller.pressed_notes)
        total_time = self._offset + max(0, session.position)
        if self.range_mode.currentIndex() == 0 and session.finished:
            total_time = max(self._offset, total_time - 1e-7)
        self._update_harmony(total_time)
        self.midi_staff.set_position(total_time, self._chord_text)
        if self.score_views.currentWidget() is self.pdf and self.auto_pdf.isChecked():
            # shortcut: PDF has no MIDI-to-symbol mapping; only the generated score has precise synchronization.
            origin = self._all_score.group_times[0]
            self._scroll_pdf((total_time - origin) / max(0.1, self._all_score.duration - origin))
        self.progress.setValue(round(max(0, session.position) / session.score.duration * 1000))
        index = min(len(session.score.groups), (bisect_right(session.score.group_times, session.position) or 1)
                    if session.preview else session.follower.index + 1)
        self.status.setText(f"Group {index} / {len(session.score.groups)} · {max(0, session.position):.1f} / {session.score.duration:.1f} s · Notes corrected: {session.follower.mistakes}")

    def _update_harmony(self, seconds):
        timeline = self._all_score.timeline
        index = timeline.measure_index(seconds)
        key = (language.code, index, math.floor(timeline.beat_at(seconds) + 1e-8), self.keyboard.start_note, self.keyboard.end_note)
        if key == self._harmony_key:
            return
        self._harmony_key = key
        names, notes = harmony_at(self._all_score, seconds)
        self._chord_text = " · ".join(names) if names else "—"
        links, tones = [], []
        for symbol in names:
            chord = parse_chord(symbol)
            title = symbol + " " + tr(quality_label(chord))
            if chord.bass:
                title += f" ({tr('Bass:')} {chord.bass})"
            links.append(f'<a href="chord:{quote(symbol, safe="")}">{escape(title)}</a>')
            tones.append(f"{symbol} · {tr('Tones:')} {' · '.join(str(note) for note in chord.notes)} · {tr('Formula:')} {'–'.join(chord.formula)}")
        description = (escape(tr("Candidates")) + ": " if len(names) > 1 else "") + " / ".join(links) if names else escape(
            tr("Rest") if not notes else tr("Single note / interval; chord undetermined") if len({note % 12 for note in notes}) < 3 else tr("Chord undetermined"))
        measure = timeline.measures[index]
        prefix = f"{tr('Bar')} {index + 1} / {len(timeline.measures)} · {measure.numerator}/{measure.denominator} · {tr('Chord reference (MIDI inference)')}: "
        self.chord_label.setText(escape(prefix) + description)
        self.chord_tones.setText("\n".join(tones))
        self.chord_tones.setVisible(bool(names))
        keys_text = tr("Score keys:") + " " + "  ".join(midi_note_name(note) for note in notes) if names else ""
        if names:
            keys_text += " · " + tr("Purple marks = chord reference, not extra keys to press. Click a chord name to learn.")
            if any(not self.keyboard.start_note <= note < self.keyboard.end_note for note in notes):
                keys_text += " " + tr("Some reference keys are outside this view; select all 88 keys to see them.")
        self.chord_keys.setText(keys_text)
        self.chord_keys.setVisible(bool(names))
        self.keyboard.set_reference_notes(frozenset(notes) if names else frozenset())
        self.chord_label.setToolTip(tr("Click a chord name to open its built-in lesson. Theory spellings can differ from key labels, such as A# and Bb sharing a key.") + "\n" +
                                   tr("Harmony uses all pitched tracks in the current quarter-note beat, not your partially pressed keys. It is a reference, not the original arranger's chord annotation.") + "\n" +
                                   " ".join(midi_note_name(note) for note in notes))

    def _open_chord_link(self, link):
        if not link.startswith("chord:"):
            return
        try:
            chord = parse_chord(unquote(link[6:]))
        except ValueError:
            return
        self.chord_requested.emit(chord.symbol)

    def _save_result(self):
        if self._saved or self.session is None or not self.session.finished or self.session.preview:
            return
        if not self.session.score.groups:
            self._queue_next_measures()
            return
        key = self.source_picker.currentData()
        metadata = {"completed": True, "corrected_notes": self.session.follower.mistakes,
                    "timing_graded": False, "speed_percent": self.speed.value()}
        metadata.update(self.hands.metadata())
        if self.source_info:
            metadata.update(source_url=self.source_info.source_url, license=self.source_info.license)
        by_bar = self.range_mode.currentIndex() == 0
        if by_bar:
            metadata.update(first_bar=self.first.value(), last_bar=self.last.value(), range_unit="bar")
        try:
            self.database.record_attempt(session_id=self.session_id, trainer_type="falling_piano", skill="score_playing",
                question=f"{key}:track:{self.track.currentData()}:{'bars:' if by_bar else ''}{self.first.value()}-{self.last.value()}" + self.hands.question_suffix(),
                expected=str(len(self.session.score.groups)), played="Completed falling-note passage",
                correct=self.session.follower.mistakes == 0, response_time_ms=round(self.session.elapsed * 1000), metadata=metadata)
        except sqlite3.Error as exc:
            self.save_button.show()
            QMessageBox.critical(self, "Database error", f"The attempt was not saved.\n\n{exc}")
            return
        self._saved = True
        self.save_button.hide()
        self.attempt_recorded.emit()
        self._queue_next_measures()
