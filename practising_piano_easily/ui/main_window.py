"""Main navigation, daily practice, settings, and session lifetime."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QLabel, QListWidget, QMessageBox, QPushButton)
from .i18n import language
from .tutorial_page import TutorialPage
from .beginner_course_page import BeginnerCoursePage
from .online_library_page import OnlineLibraryPage
from .falling_piano_page import FallingPianoPage
from .score_practice_page import ScorePracticePage

from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.progress import daily_plan, dashboard_report, session_report
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS, completed_lessons, next_lesson_index

from .chord_trainer_page import ChordTrainerPage
from .composition_page import CompositionPage
from .ear_training_page import EarTrainingPage
from .harmony_page import HarmonyPage
from .midi_monitor import MidiMonitorPage
from .progress_page import ProgressPage
from .settings_page import SettingsPage
from .song_analysis_page import SongAnalysisPage
from .theory_practice_page import TheoryPracticePage
from .voice_leading_page import VoiceLeadingPage


class HomePage(QWidget):
    practice_requested = Signal()
    beginner_requested = Signal()
    end_requested = Signal()

    def __init__(self, database: Database, session_id: int) -> None:
        super().__init__()
        self.database = database
        self.session_id = session_id
        layout = QVBoxLayout(self)
        title = QLabel("practising piano easily")
        title.setStyleSheet("font-size: 32px; font-weight: 700")
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("font-size: 16px; color: #64748b")
        self.progress = QLabel()
        self.progress.setStyleSheet("font-size: 18px; padding: 20px")
        self.plan = QLabel()
        self.plan.setWordWrap(True)
        self.beginner_summary = QLabel()
        self.beginner_summary.setWordWrap(True)
        self.continue_beginner = QPushButton("Continue beginner course")
        self.continue_beginner.setStyleSheet("font-size: 20px; padding: 14px; font-weight: 700;")
        self.continue_beginner.clicked.connect(self.beginner_requested)
        buttons = QHBoxLayout()
        for minutes in (15, 30, 45):
            button = QPushButton(f"Start {minutes} min")
            button.clicked.connect(lambda checked=False, value=minutes: self._start_plan(value))
            buttons.addWidget(button)
        end = QPushButton("End Session")
        end.clicked.connect(self.end_requested)
        buttons.addWidget(end)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.continue_beginner)
        layout.addWidget(self.beginner_summary)
        layout.addWidget(self.progress)
        layout.addLayout(buttons)
        layout.addWidget(self.plan)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        report = dashboard_report(self.database)
        stage = self.database.get_setting("curriculum_stage", "1")
        self.subtitle.setText(f"Curriculum Stage {stage} · manually controlled")
        completed = completed_lessons(self.database)
        count = len(completed & {lesson.id for lesson in LESSONS})
        self.beginner_summary.setText(
            f"Lessons completed: {count} / {len(LESSONS)}\nContinue: {LESSONS[next_lesson_index(self.database)].title}\n"
            "Read the score, find the keys, and correct them at your own pace."
        )
        weakest = min(report["skill_accuracy"], key=report["skill_accuracy"].get) if report["skill_accuracy"] else "—"
        self.progress.setText(
            f"All-time attempts: {report['attempts']}\nAccuracy: {report['accuracy']:.1f}%\n"
            f"Average response: {report['average_response_ms'] / 1000:.1f} s\nWeak item group: {weakest}"
        )

    def _start_plan(self, minutes: int) -> None:
        report = dashboard_report(self.database)
        weakest = min(report["skill_accuracy"], key=report["skill_accuracy"].get) if report["skill_accuracy"] else None
        stage = int(self.database.get_setting("curriculum_stage", "1"))
        plan = daily_plan(minutes, stage, weakest)
        self.database.set_session_preset(self.session_id, minutes)
        self.plan.setText("Today: " + " · ".join(f"{name} {length} min" for name, length in plan))
        self.practice_requested.emit()


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        language.set_language(database.get_setting("language", "zh_CN"))
        self.session_id = database.start_session()
        self.controller = MidiController()
        self._session_ended = False
        self._skip_summary = False
        self._before_falling_geometry = None
        self._tutorial_return_to_falling = False
        self.setWindowTitle("practising piano easily")
        self.resize(1160, 780)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(190)
        self.navigation.addItems([
            "Home", "Chord Trainer", "Theory Practice", "Ear Training", "Harmony",
            "Voice Leading", "Song Analysis", "Composition", "Progress", "Settings", "MIDI Monitor", "Chord Tutorial",
            "Beginner course & sheet music",
            "Online score library",
            "Falling piano",
            "Score practice",
        ])
        self.pages = QStackedWidget()
        self.home = HomePage(database, self.session_id)
        self.trainer = ChordTrainerPage(self.controller, database, self.session_id)
        self.theory_practice = TheoryPracticePage(self.controller, database, self.session_id)
        self.ear_training = EarTrainingPage(database, self.session_id)
        self.harmony = HarmonyPage(self.controller, database, self.session_id)
        self.voice_leading = VoiceLeadingPage()
        self.song_analysis = SongAnalysisPage()
        self.composition = CompositionPage()
        self.progress = ProgressPage(database)
        self.settings = SettingsPage(database, self.controller)
        self.monitor = MidiMonitorPage(self.controller)
        self.tutorial = TutorialPage(database, self.session_id, self.ear_training.synth)
        self.beginner = BeginnerCoursePage(self.controller, database, self.session_id, self.ear_training.synth)
        self.score_practice = ScorePracticePage(self.controller, database, self.session_id)
        self.online_library = OnlineLibraryPage(self.controller, database, self.session_id, practice=self.score_practice.practice)
        self.online_library.practice_requested.connect(self._library_practice_requested)
        self.score_practice.library_requested.connect(self._import_score)
        self.online_library.score_available.connect(self.score_practice.add_downloaded)
        self.falling = FallingPianoPage(self.controller, database, self.session_id)
        self.online_library.score_available.connect(self.falling.add_downloaded)
        self.falling.chord_requested.connect(self._open_chord_help)
        self.beginner.falling_requested.connect(self._open_falling_lesson)
        self.online_library.practice.falling_requested.connect(self._open_falling_downloaded)
        self.online_library.practice.lesson_falling_requested.connect(self._open_falling_practice_lesson)
        self.beginner.midi_setup_requested.connect(lambda: self.navigation.setCurrentRow(self.pages.indexOf(self.monitor)))
        self.tutorial.practice_requested.connect(self._tutorial_practice)
        for page in (self.home, self.trainer, self.theory_practice, self.ear_training, self.harmony, self.voice_leading,
                     self.song_analysis, self.composition, self.progress, self.settings, self.monitor, self.tutorial, self.beginner, self.online_library, self.falling, self.score_practice):
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.currentRowChanged.connect(lambda index: self.progress.refresh() if index == 8 else None)
        for page in (self.trainer, self.theory_practice, self.ear_training, self.harmony, self.tutorial, self.beginner, self.online_library, self.falling):
            page.attempt_recorded.connect(self.home.refresh)
            page.attempt_recorded.connect(self.progress.refresh)
        self.home.beginner_requested.connect(self._open_beginner)
        self.home.practice_requested.connect(self._start_daily_practice)
        self.home.end_requested.connect(self.close)
        self.settings.settings_saved.connect(self._apply_settings)
        self.navigation.setCurrentRow(0)

        central = QWidget()
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        beginner_button = QPushButton("Beginner course & sheet music")
        beginner_button.clicked.connect(self._open_beginner)
        top.addWidget(beginner_button)
        tutorial_button = QPushButton("Chord Tutorial")
        tutorial_button.clicked.connect(lambda: self.navigation.setCurrentRow(self.pages.indexOf(self.tutorial)))
        top.addWidget(tutorial_button)
        online_button = QPushButton("Online score library")
        online_button.clicked.connect(lambda: self.navigation.setCurrentRow(self.pages.indexOf(self.online_library)))
        top.addWidget(online_button)
        falling_button = QPushButton("Falling piano")
        falling_button.clicked.connect(lambda: self.navigation.setCurrentRow(self.pages.indexOf(self.falling)))
        top.addWidget(falling_button)
        score_button = QPushButton("Score practice")
        score_button.clicked.connect(self._open_score_practice)
        top.addWidget(score_button)
        top.addStretch()
        top.addWidget(QLabel("Language / 语言"))
        self.language_selector = QComboBox()
        self.language_selector.addItem("简体中文", "zh_CN")
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("日本語", "ja")
        self.language_selector.setCurrentIndex(max(0, self.language_selector.findData(language.code)))
        self.language_selector.currentIndexChanged.connect(self._change_language)
        top.addWidget(self.language_selector)
        layout.addLayout(top)
        content = QHBoxLayout()
        content.addWidget(self.navigation)
        content.addWidget(self.pages, 1)
        layout.addLayout(content, 1)
        self.setCentralWidget(central)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)
        self._apply_settings(self.settings.values())
        self.controller.refresh_devices()

    def _apply_settings(self, values: dict[str, str]) -> None:
        language.set_language(values["language"])
        with QSignalBlocker(self.language_selector):
            self.language_selector.setCurrentIndex(self.language_selector.findData(language.code))
        self.trainer.settling.setValue(int(values["settling_ms"]))
        self.trainer.level.setCurrentIndex(int(values["difficulty"]) - 1)
        octaves = int(values["octaves"])
        for keyboard in (self.trainer.keyboard, self.theory_practice.keyboard, self.harmony.widget(1).keyboard):
            keyboard.start_note = 48
            keyboard.end_note = min(108, 48 + 12 * octaves)
            keyboard.update()
        self.ear_training.volume.setValue(int(values["ear_volume"]))
        self.trainer.question_limit = int(values["question_count"])
        self.theory_practice.question_limit = int(values["question_count"])
        self.ear_training.question_limit = int(values["question_count"])
        self.ear_training.synth.device = int(values["audio_output"]) if values["audio_output"] else None
        self.monitor.notation_preference = values["notation"]
        self.home.refresh()

    def _change_language(self) -> None:
        code = self.language_selector.currentData()
        try:
            self.database.set_setting("language", code)
        except sqlite3.Error as exc:
            with QSignalBlocker(self.language_selector):
                self.language_selector.setCurrentIndex(self.language_selector.findData(language.code))
            QMessageBox.critical(self, "Database error", str(exc))
            return
        language.set_language(code)
        self.settings.language.setCurrentIndex(self.settings.language.findData(code))

    def _open_beginner(self):
        self.beginner.resume_next()
        self.navigation.setCurrentRow(self.pages.indexOf(self.beginner))

    def _navigate(self, index):
        self.pages.setCurrentIndex(index)
        if self.pages.currentWidget() is not self.tutorial:
            self._tutorial_return_to_falling = False
        if self.pages.currentWidget() is self.falling:
            if not self.isMaximized():
                self._before_falling_geometry = self.geometry()
                self.showMaximized()
        elif self._before_falling_geometry is not None:
            geometry, self._before_falling_geometry = self._before_falling_geometry, None
            if self.isMaximized():
                self.showNormal()
                self.setGeometry(geometry)

    def _open_falling_lesson(self, lesson):
        self.falling.open_lesson(lesson)
        self.navigation.setCurrentRow(self.pages.indexOf(self.falling))

    def _open_score_practice(self):
        self.navigation.setCurrentRow(self.pages.indexOf(self.score_practice))

    def _library_practice_requested(self):
        if self.pages.currentWidget() is self.online_library:
            self._open_score_practice()

    def _import_score(self):
        self.navigation.setCurrentRow(self.pages.indexOf(self.online_library))
        self.online_library.open_import()

    def _open_falling_practice_lesson(self, payload):
        lesson, first, last, hand, split = payload
        with QSignalBlocker(self.falling.hands.hand), QSignalBlocker(self.falling.hands.split):
            self.falling.hands.hand.setCurrentIndex(self.falling.hands.hand.findData(hand))
            self.falling.hands.split.setValue(split)
        self._open_falling_lesson(lesson)
        self.falling._set_bar_range(first, last)
        self.falling.hands.save_options()

    def _open_falling_downloaded(self, payload):
        self.falling.open_downloaded(payload)
        self.navigation.setCurrentRow(self.pages.indexOf(self.falling))

    def _open_chord_help(self, symbol):
        self.tutorial.open_chord(symbol)
        self._tutorial_return_to_falling = True
        self.navigation.setCurrentRow(self.pages.indexOf(self.tutorial))

    def _escape(self):
        if self.pages.currentWidget() is self.tutorial and self._tutorial_return_to_falling:
            self.navigation.setCurrentRow(self.pages.indexOf(self.falling))
            self.falling.resume_after_countdown()
        else:
            self.navigation.setCurrentRow(0)

    def _start_daily_practice(self):
        if int(self.database.get_setting("curriculum_stage", "1")) <= 2:
            self._open_beginner()
        else:
            self.navigation.setCurrentRow(self.pages.indexOf(self.trainer))

    def _tutorial_practice(self, example) -> None:
        if self.controller.pressed_notes:
            QMessageBox.information(self, "Chord Tutorial", "Release all keys before moving to the next chord.")
            return
        from practising_piano_easily.core import parse_chord

        self.trainer.timer.stop()
        self.trainer.level.setCurrentIndex(example.level - 1)
        self.trainer.trainer.next_question()
        self.trainer.trainer.current_chord = parse_chord(example.symbol)
        self.trainer.mode.setCurrentIndex(1 if self.trainer.trainer.current_chord.bass else 0)
        self.trainer.training_mode.setCanonicalText("Learn")
        self.trainer._show_question()
        self.navigation.setCurrentRow(1)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.falling.pause()
        self.falling.hands.save_options()
        self.score_practice.practice.hands.save_options()
        self.falling.notation_controls.save_options()
        self.online_library.practice.notation_controls.save_options()
        self.online_library.practice.save_loop_option()
        self.falling.save_practice_options()
        self.falling.save_last_song()
        self.controller.close()
        if not self._session_ended:
            self.database.end_session(self.session_id)
            report = session_report(self.database, self.session_id)
            self._session_ended = True
            if not self._skip_summary:
                QMessageBox.information(
                    self, "Session report",
                    f"Attempts: {report['attempts']}\nAccuracy: {report['accuracy']:.1f}%\n"
                    f"Average response: {report['average_response_ms'] / 1000:.2f} s\n"
                    f"Best skill: {report['best_skill'] or '—'}\nWeakest skill: {report['weakest_skill'] or '—'}\n"
                    f"New mistakes: {', '.join(report['new_mistakes']) or '—'}\n"
                    f"Improved items: {', '.join(report['improved_items']) or '—'}\n"
                    f"Suggested next practice: {report['suggested_next_practice']}",
                )
        self.database.close()
        event.accept()
