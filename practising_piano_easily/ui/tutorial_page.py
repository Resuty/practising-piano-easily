"""Offline multilingual lessons, audible examples, and scored chapter quizzes."""

import sqlite3
import time

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QTextBrowser, QSplitter

from practising_piano_easily.trainers.chord_construction import midi_note_name
from practising_piano_easily.tutorial import Example, load_lessons
from practising_piano_easily.core import parse_chord
from practising_piano_easily.chord_learning import quality_label, tutorial_topic

from .keyboard_widget import PianoKeyboard
from .localized_widgets import QLabel, QPushButton, QComboBox, QCheckBox, QMessageBox
from .i18n import language, tr


class TutorialPage(QWidget):
    practice_requested = Signal(object)
    attempt_recorded = Signal()

    def __init__(self, database, session_id, synth):
        super().__init__()
        self.database, self.session_id, self.synth = database, session_id, synth
        self.lessons = load_lessons()
        self.japanese_lessons = load_lessons("ja")
        self.english_lessons = load_lessons("en")
        self._answers = {}
        self._linked_example = None
        self._linked_symbol = None
        self._started = time.monotonic()
        layout = QVBoxLayout(self)
        title = QLabel("Chord Tutorial")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        layout.addWidget(QLabel("Tutorial content: Simplified Chinese · Read, listen, play, then test yourself."))
        row = QHBoxLayout()
        self.chapter = QComboBox()
        self.chapter.addItems([lesson.title for lesson in self.lessons])
        previous = QPushButton("Previous chapter")
        following = QPushButton("Next chapter")
        previous.clicked.connect(lambda: self.chapter.setCurrentIndex(max(0, self.chapter.currentIndex() - 1)))
        following.clicked.connect(lambda: self.chapter.setCurrentIndex(min(len(self.lessons) - 1, self.chapter.currentIndex() + 1)))
        row.addWidget(previous)
        row.addWidget(self.chapter, 1)
        row.addWidget(following)
        layout.addLayout(row)

        self.reader = QTextBrowser()
        self.reader.setOpenExternalLinks(True)
        self.reader.setStyleSheet("QTextBrowser {font-size: 16px; background: #ffffff; color: #172033; padding: 14px;}")
        self.reader.document().setDefaultStyleSheet("h1 {color:#174d66;} h2 {color:#22566b;} p {line-height:150%;} th, td {padding:7px;}")
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("Keyboard example"))
        self.example = QComboBox()
        side_layout.addWidget(self.example)
        self.example_notes = QLabel()
        self.example_notes.setWordWrap(True)
        side_layout.addWidget(self.example_notes)
        self.keyboard = PianoKeyboard(48, 84)
        self.keyboard.setFixedHeight(150)
        self.keyboard.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        side_layout.addWidget(self.keyboard)
        example_buttons = QHBoxLayout()
        play = QPushButton("Play example")
        practice = QPushButton("Practice this chord")
        play.clicked.connect(self._play)
        practice.clicked.connect(lambda: self.practice_requested.emit(self.current_example))
        example_buttons.addWidget(play)
        example_buttons.addWidget(practice)
        side_layout.addLayout(example_buttons)
        self.audio_status = QLabel()
        self.audio_status.setWordWrap(True)
        side_layout.addWidget(self.audio_status)

        side_layout.addWidget(QLabel("Chapter self-test"))
        self.quiz = QComboBox()
        self.quiz.currentIndexChanged.connect(self._show_quiz)
        side_layout.addWidget(self.quiz)
        self.question = QLabel()
        self.question.setWordWrap(True)
        self.question.setStyleSheet("font-size: 16px; font-weight: 600;")
        side_layout.addWidget(self.question)
        self.choices = QComboBox()
        self.choices.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.choices.setMinimumContentsLength(18)
        side_layout.addWidget(self.choices)
        self.submit = QPushButton("Submit answer")
        self.submit.clicked.connect(self._submit)
        side_layout.addWidget(self.submit)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        side_layout.addWidget(self.feedback)
        self.read = QCheckBox("Mark chapter as read (not mastery)")
        self.read.toggled.connect(self._mark_read)
        side_layout.addWidget(self.read)
        self.read_count = QLabel()
        side_layout.addWidget(self.read_count)
        side_layout.addStretch()
        split = QSplitter()
        split.addWidget(self.reader)
        split.addWidget(side)
        split.setSizes([690, 390])
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.example.currentIndexChanged.connect(self._show_example)
        self.chapter.currentIndexChanged.connect(self._change_chapter)
        last = self.database.get_setting("tutorial_chapter", self.lessons[0].id)
        index = next((i for i, lesson in enumerate(self.lessons) if lesson.id == last), 0)
        self.chapter.blockSignals(True)
        self.chapter.setCurrentIndex(index)
        self.chapter.blockSignals(False)
        self._render_chapter()
        language.changed.connect(self._refresh_linked_intro)

    @property
    def lesson(self):
        return self.lessons[self.chapter.currentIndex()]

    @property
    def current_example(self):
        if self._linked_example and self.example.currentIndex() == len(self.lesson.examples):
            return self._linked_example
        return self.lesson.examples[max(0, self.example.currentIndex())]

    def open_chord(self, symbol):
        from practising_piano_easily.composition import ProgressionChord, make_voicing
        from practising_piano_easily.trainers.chord_construction import LEVEL_SUFFIXES

        chord = parse_chord(symbol)
        chapter = next(index for index, lesson in enumerate(self.lessons) if lesson.id == tutorial_topic(chord))
        if chapter == self.chapter.currentIndex():
            self._render_chapter()
        else:
            self.chapter.setCurrentIndex(chapter)
        index = next((index for index, example in enumerate(self.lesson.examples) if example.symbol == chord.symbol), -1)
        if index < 0:
            level = next((level for level, suffixes in LEVEL_SUFFIXES.items() if chord.canonical_suffix in suffixes), 1)
            self._linked_example = Example(chord.symbol, make_voicing(ProgressionChord(chord.symbol)), level)
            self.example.addItem(chord.symbol)
            index = self.example.count() - 1
        self._linked_symbol = chord.symbol
        self.keyboard.label_all_notes = True
        self.example.setCurrentIndex(index)
        self._show_example()
        self._refresh_linked_intro()

    def _refresh_linked_intro(self):
        scroll = self.reader.verticalScrollBar().value()
        if self._linked_symbol is None:
            self.reader.setMarkdown(self._chapter_markdown())
            self.reader.verticalScrollBar().setValue(scroll)
            return
        chord = parse_chord(self._linked_symbol)
        intro = (f"## {tr('Chord opened from the score:')} {chord.symbol} {tr(quality_label(chord))}\n\n"
                 f"**{tr('Tones:')}** {' · '.join(str(note) for note in chord.notes)}  \n"
                 f"**{tr('Formula:')}** {'–'.join(chord.formula)}\n\n")
        if chord.bass:
            intro += f"**{tr('Bass:')}** {chord.bass}\n\n"
        intro += tr("These tones are in root-based order. The keyboard example is one possible voicing, not a requirement to add notes to the score. Read the related chapter below.") + "\n\n---\n\n"
        self.reader.setMarkdown(intro + self._chapter_markdown())
        self.reader.verticalScrollBar().setValue(scroll)

    def _chapter_markdown(self):
        lessons = {"ja": self.japanese_lessons, "en": self.english_lessons}.get(language.code, self.lessons)
        return lessons[self.chapter.currentIndex()].markdown

    def _save(self, key, value):
        try:
            self.database.set_setting(key, value)
            return True
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", str(exc))
            return False

    def _change_chapter(self):
        self._save("tutorial_chapter", self.lesson.id)
        self._render_chapter()

    def _render_chapter(self):
        self._linked_example = self._linked_symbol = None
        self.keyboard.label_all_notes = False
        self.reader.setMarkdown(self._chapter_markdown())
        self.reader.verticalScrollBar().setValue(0)
        self.example.blockSignals(True)
        self.example.clear()
        self.example.addItems([example.symbol for example in self.lesson.examples])
        self.example.blockSignals(False)
        self._show_example()
        self.quiz.blockSignals(True)
        self.quiz.clear()
        self.quiz.addItems([f"{index + 1} / {len(self.lesson.quizzes)}" for index in range(len(self.lesson.quizzes))])
        self.quiz.blockSignals(False)
        self._show_quiz()
        self.read.blockSignals(True)
        self.read.setChecked(self.database.get_setting(f"tutorial_read_{self.lesson.id}", "0") == "1")
        self.read.blockSignals(False)
        self._read_count()

    def _show_example(self):
        example = self.current_example
        chord = parse_chord(example.symbol)
        self.keyboard.start_note = min(48, min(example.notes) // 12 * 12)
        self.keyboard.end_note = max(84, max(example.notes) + 1)
        notes = frozenset(example.notes)
        self.keyboard.set_notes(notes, correct=notes)
        self.example_notes.setText(example.symbol + " = " + "  ".join(midi_note_name(note, None if self._linked_symbol else chord) for note in example.notes))
        if self._linked_symbol and self._linked_symbol != example.symbol:
            self._linked_symbol = example.symbol
            self._refresh_linked_intro()
        self.audio_status.clear()

    def _play(self):
        try:
            volume = int(self.database.get_setting("ear_volume", "25")) / 100
            self.synth.play((self.current_example.notes,), volume=volume)
            self.audio_status.setText("Listen, then play the same notes yourself.")
        except Exception as exc:
            self.audio_status.setText(f"Audio device unavailable: {exc}")

    def _show_quiz(self):
        index = self.quiz.currentIndex()
        if index < 0:
            return
        quiz = self.lesson.quizzes[index]
        self.question.setText(quiz.question)
        self.choices.clear()
        self.choices.addItems(quiz.options)
        self.choices.setCurrentIndex(-1)
        answer = self._answers.get((self.lesson.id, index))
        self.submit.setEnabled(answer is None)
        self.feedback.setText(answer or "Choose an answer before submitting.")
        self._started = time.monotonic()

    def _submit(self):
        index = self.quiz.currentIndex()
        key = (self.lesson.id, index)
        if key in self._answers:
            return
        choice = self.choices.currentIndex()
        if choice < 0:
            self.feedback.setText("Choose an answer before submitting.")
            return
        quiz = self.lesson.quizzes[index]
        correct = choice == quiz.answer
        try:
            self.database.record_attempt(
                session_id=self.session_id, trainer_type="tutorial", skill="chord_tutorial",
                question=f"tutorial:{self.lesson.id}:{index + 1}", expected=quiz.options[quiz.answer],
                played=quiz.options[choice], correct=correct,
                response_time_ms=max(0, round((time.monotonic() - self._started) * 1000)),
                metadata={"chapter": self.lesson.id, "question_text": quiz.question},
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"The answer was not saved.\n\n{exc}")
            return
        feedback = ("Correct" if correct else "Wrong") + "\n" + quiz.explanation
        self._answers[key] = feedback
        self.feedback.setText(feedback)
        self.submit.setEnabled(False)
        self.attempt_recorded.emit()

    def _mark_read(self, checked):
        if not self._save(f"tutorial_read_{self.lesson.id}", "1" if checked else "0"):
            self.read.blockSignals(True)
            self.read.setChecked(not checked)
            self.read.blockSignals(False)
        self._read_count()

    def _read_count(self):
        count = sum(self.database.get_setting(f"tutorial_read_{lesson.id}", "0") == "1" for lesson in self.lessons)
        self.read_count.setText(f"Chapters read: {count} / {len(self.lessons)}")
