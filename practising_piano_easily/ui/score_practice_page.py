"""Direct score-practice workspace, sharing the one MIDI follower used by library imports."""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QComboBox

from practising_piano_easily.analysis.online_scores import downloaded_scores, score_folder
from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES
from .downloaded_score_page import DownloadedScorePage
from .localized_widgets import QLabel, QPushButton
from .i18n import language, tr


class ScorePracticePage(QWidget):
    library_requested = Signal()

    def __init__(self, controller, database, session_id):
        super().__init__()
        self._entries, self._added = {}, {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        heading = QLabel("Score practice")
        heading.setStyleSheet("font-size: 24px; font-weight: 700")
        row.addWidget(heading)
        self.source_picker = QComboBox()
        self.source_picker.setMinimumContentsLength(16)
        self.source_picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row.addWidget(self.source_picker, 1)
        refresh = QPushButton("Refresh library")
        refresh.clicked.connect(self.refresh_sources)
        row.addWidget(refresh)
        import_button = QPushButton("Browser downloads / import files")
        import_button.clicked.connect(self.library_requested)
        row.addWidget(import_button)
        layout.addLayout(row)
        self.practice = DownloadedScorePage(controller, database, session_id)
        layout.addWidget(self.practice, 1)
        self.practice.score_opened.connect(self._opened)
        self.source_picker.currentIndexChanged.connect(self._select_source)
        language.changed.connect(self._retranslate)
        self.refresh_sources()

    def _title(self, item, folder):
        return tr("Local score" if folder else "Course" if item in LESSONS else "Repertoire") + " · " + (item.title if folder else tr(item.title))

    def refresh_sources(self):
        key = self.source_picker.currentData()
        self._entries = {"builtin:" + item.id: (item, None) for item in LESSONS + PIECES}
        self._entries.update({f"{item.provider}:{item.id}": (item, score_folder(item)) for item in downloaded_scores()})
        self._entries.update(self._added)
        with QSignalBlocker(self.source_picker):
            self.source_picker.clear()
            for item_key, (item, folder) in self._entries.items():
                self.source_picker.addItem(self._title(item, folder), item_key)
            self.source_picker.setCurrentIndex(max(0, self.source_picker.findData(key)))
        if key != self.source_picker.currentData():
            self._select_source()

    def _opened(self, payload):
        item, folder = payload
        key = "builtin:" + item.id if folder is None else f"{item.provider}:{item.id}"
        if folder is not None:
            self._added[key] = (item, folder)
        self._entries[key] = (item, folder)
        with QSignalBlocker(self.source_picker):
            index = self.source_picker.findData(key)
            if index < 0:
                self.source_picker.addItem(self._title(item, folder), key)
                index = self.source_picker.count() - 1
            self.source_picker.setCurrentIndex(index)

    def add_downloaded(self, payload):
        item, folder = payload
        key = f"{item.provider}:{item.id}"
        self._added[key] = self._entries[key] = (item, folder)
        with QSignalBlocker(self.source_picker):
            if self.source_picker.findData(key) < 0:
                self.source_picker.addItem(self._title(item, folder), key)

    def _select_source(self):
        item, folder = self._entries[self.source_picker.currentData()]
        try:
            if folder is None:
                self.practice.open_lesson(item)
            else:
                self.practice.open_score(item, folder)
        except (OSError, ValueError) as exc:
            self.practice._running = self.practice._repeat_pending = False
            self.practice.start.setEnabled(False)
            self.practice.falling_button.setEnabled(False)
            self.practice.feedback.setText(str(exc))

    def _retranslate(self):
        with QSignalBlocker(self.source_picker):
            for index in range(self.source_picker.count()):
                self.source_picker.setItemText(index, self._title(*self._entries[self.source_picker.itemData(index)]))

    def showEvent(self, event):
        self.refresh_sources()
        super().showEvent(event)
