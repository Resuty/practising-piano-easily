"""On-demand catalog searches, permitted downloads and shared offline score practice."""

import threading

from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem, QAbstractItemView

from practising_piano_easily.analysis.online_scores import (search_scores, download_score, downloaded_scores, score_folder,
                                                       SOURCE_NAMES, POLICY_URLS, checked_url)
from practising_piano_easily.analysis.fan_scores import search_ichigos
from .localized_widgets import QLabel, QLineEdit, QPushButton, QTableWidget, QTabWidget, QComboBox, QCheckBox
from .i18n import language, tr
from .downloaded_score_page import DownloadedScorePage
from .musescore_page import MuseScorePage


class OnlineLibraryPage(QTabWidget):
    attempt_recorded = Signal()
    score_available = Signal(object)
    search_ready = Signal(object)
    download_ready = Signal(object)
    network_error = Signal(str)
    practice_requested = Signal()

    def __init__(self, controller, database, session_id, *, practice=None):
        super().__init__()
        self.scores = []
        self.offset = 0
        self.busy = False
        self._view = "start"
        self._results = []
        self._search_query = ""
        library = QWidget()
        layout = QVBoxLayout(library)
        title = QLabel("Anime, game and classical piano scores")
        title.setStyleSheet("font-size: 25px; font-weight: 700")
        layout.addWidget(title)
        info = QLabel("Ichigo's supports in-app anime/game search and personal-use downloads. NinSheetMusic opens a browser search and local import because of its security checks. Mutopia remains available for classical music. PDF alone cannot detect keys.")
        info.setWordWrap(True)
        layout.addWidget(info)
        row = QHBoxLayout()
        self.provider = QComboBox()
        for provider in ("ichigos", "ninsheetmusic", "mutopia"):
            self.provider.addItem(SOURCE_NAMES[provider], provider)
        self.query = QLineEdit("Angel Beats")
        self.query.setPlaceholderText("Anime / game / song title; English or romanized names work best")
        self.search_button = QPushButton("Search online")
        self.search_button.clicked.connect(lambda: self.search(0))
        self.query.returnPressed.connect(lambda: self.search(0))
        self.local_button = QPushButton("Downloaded scores")
        self.local_button.clicked.connect(self.show_downloaded)
        row.addWidget(self.provider); row.addWidget(self.query, 1); row.addWidget(self.search_button); row.addWidget(self.local_button)
        layout.addLayout(row)
        filters = QHBoxLayout()
        self.pairs_only = QCheckBox("Only show matching PDF + MIDI pairs")
        self.pairs_only.setChecked(True)
        self.pairs_only.toggled.connect(self._filter_changed)
        self.import_button = QPushButton("Browser downloads / import files")
        self.import_button.clicked.connect(self.open_import)
        filters.addWidget(self.pairs_only)
        filters.addStretch()
        filters.addWidget(self.import_button)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Title", "Composer / arranger", "Source", "Files", "License", "Downloaded"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        self.previous = QPushButton("Previous results")
        self.previous.clicked.connect(lambda: self.search(max(0, self.offset - 10)))
        self.next = QPushButton("More results")
        self.next.clicked.connect(lambda: self.search(self.offset + 10))
        self.download_button = QPushButton("Download / open for practice")
        self.download_button.clicked.connect(self.download_selected)
        self.source_button = QPushButton("View source and credits")
        self.source_button.clicked.connect(self.open_source)
        for button in (self.previous, self.next, self.source_button, self.download_button):
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.personal_use = QCheckBox("Personal non-commercial practice only; keep credits and do not redistribute these scores")
        self.personal_use.toggled.connect(self._selection_changed)
        layout.addWidget(self.personal_use)
        policy_button = QPushButton("Read site usage and credits")
        policy_button.clicked.connect(self.open_policy)
        layout.addWidget(policy_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._external_practice = practice is not None
        self.practice = practice if practice is not None else DownloadedScorePage(controller, database, session_id)
        self.practice.attempt_recorded.connect(self.attempt_recorded)
        self.addTab(library, "Search / downloaded scores")
        if self._external_practice:
            practice_entry = QWidget()
            entry_layout = QVBoxLayout(practice_entry)
            entry_layout.addWidget(QLabel("Score practice has its own page. Open it directly from the top bar or sidebar."))
            open_practice = QPushButton("Score practice")
            open_practice.clicked.connect(self.practice_requested)
            entry_layout.addWidget(open_practice)
            entry_layout.addStretch()
            self.addTab(practice_entry, "Read and practice")
        else:
            self.addTab(self.practice, "Read and practice")
        self.musescore = MuseScorePage()
        self.musescore.imported.connect(self._download_done)
        self.addTab(self.musescore, "Browser search / file import")
        self.search_ready.connect(self._search_done)
        self.download_ready.connect(self._download_done)
        self.network_error.connect(self._error)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        language.changed.connect(lambda: self._show_scores(self.scores))
        self._provider_changed()

    def _set_busy(self, value):
        self.busy = value
        for button in (self.search_button, self.local_button, self.import_button, self.provider, self.query, self.pairs_only):
            button.setEnabled(not value)
        self._selection_changed()
        self._paging()

    def _provider_changed(self):
        self._view = "start"
        self.offset = 0
        self._results = []
        self.personal_use.setChecked(False)
        self._show_scores([])
        self._paging()
        browser = self.provider.currentData() == "ninsheetmusic"
        if self.query.text() in {"Angel Beats", "Genshin Impact", "Schumann"}:
            self.query.setText({"ichigos": "Angel Beats", "ninsheetmusic": "Genshin Impact", "mutopia": "Schumann"}[self.provider.currentData()])
        self.search_button.setText("Search in browser" if browser else "Search online")
        self.status.setText("NinSheetMusic requires browser verification. Search opens a site-restricted web search; download PDF + MIDI on the original site and use Import files here." if browser else
                            "Enter a title and search. Results are loaded on demand; nothing is downloaded automatically.")

    def _paging(self):
        online = self._view == "online" and not self.busy
        self.previous.setEnabled(online and self.offset > 0)
        more = (self.offset + 10 < len(self._filtered_results())) if self.provider.currentData() == "ichigos" else len(self._results) == 10
        self.next.setEnabled(online and more)

    def _filtered_results(self):
        return [score for score in self._results if not self.pairs_only.isChecked() or (score.pdf_url and score.midi_url)]

    def _filter_changed(self):
        if self._view == "online" and self.provider.currentData() == "ichigos":
            self.offset = 0
            self._render_results()

    def search(self, offset):
        if self.busy:
            return
        provider = self.provider.currentData()
        if provider == "ninsheetmusic":
            self.open_import()
            self.musescore.open_search()
            return
        query = self.query.text().strip() if offset == 0 else self._search_query
        if provider == "ichigos" and not query:
            self.status.setText("Enter an anime, game or song title first")
            return
        self.offset = offset
        self._search_query = query
        if provider == "ichigos" and offset > 0:
            self._render_results()
            return
        self._set_busy(True)
        self.status.setText("Searching " + SOURCE_NAMES[provider] + "…")

        def worker():
            try:
                self.search_ready.emit(search_ichigos(query) if provider == "ichigos" else search_scores(query, offset))
            except Exception as exc:
                self.network_error.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _search_done(self, scores):
        self._view = "online"
        self._results = scores
        self._set_busy(False)
        self._render_results()

    def _render_results(self):
        scores = self._filtered_results()
        if self.provider.currentData() == "ichigos":
            self._show_scores(scores[self.offset:self.offset + 10])
            ready = sum(bool(score.pdf_url and score.midi_url) for score in self._results)
            self.status.setText(f"Results: {len(self._results)} · PDF + MIDI pairs: {ready} · Shown: {len(self.scores)} · Uncheck the pair filter to see PDF-only editions. Use English or romanized titles if no results appear.")
        else:
            self._show_scores(scores)
            self.status.setText(f"Results: {len(scores)} · Only editions with PDF, MIDI and a stated open license are listed. Use More results for the next page; this is not the full catalog.")
        self._paging()

    def show_downloaded(self):
        if self.busy:
            return
        self._view = "downloaded"
        self._show_scores(downloaded_scores())
        self._paging()
        self.status.setText("Downloaded scores are available offline. Search online to find more.")

    def _show_scores(self, scores):
        row = self.table.currentRow()
        selected = self.scores[row] if 0 <= row < len(self.scores) else None
        self.scores = scores
        self.table.setRowCount(len(scores))
        for row, score in enumerate(scores):
            folder = score_folder(score)
            downloaded = all((folder / name).is_file() for name in ("score.mid", "source.json"))
            files = "PDF + MIDI" if (downloaded and (folder / "score.pdf").is_file()) or (score.pdf_url and score.midi_url) else "MIDI only" if downloaded or score.midi_url else "PDF only"
            for column, value in enumerate((score.title, score.composer, tr(SOURCE_NAMES[score.provider]), tr(files), tr(score.license), "✓" if downloaded else "—")):
                item = QTableWidgetItem(value)
                item.setToolTip(value + ("\n" + score.instrumentation if column == 0 and score.instrumentation else ""))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, min(330, max(200, self.table.columnWidth(0))))
        self.table.setColumnWidth(4, 175)
        if scores:
            self.table.selectRow(next((index for index, score in enumerate(scores)
                                       if selected and (score.provider, score.id) == (selected.provider, selected.id)), 0))
        self._selection_changed()

    def _selection_changed(self):
        row = self.table.currentRow()
        score = self.scores[row] if 0 <= row < len(self.scores) else None
        cached = bool(score and all((score_folder(score) / name).is_file() for name in ("score.mid", "source.json")))
        needs_permission = bool(score and score.provider == "ichigos" and not cached)
        self.personal_use.setVisible(needs_permission)
        ready = bool(score and (cached or (score.pdf_url and score.midi_url)))
        self.download_button.setEnabled(not self.busy and ready and (not needs_permission or self.personal_use.isChecked()))
        self.source_button.setEnabled(bool(score and score.source_url and score.provider != "local"))

    def download_selected(self):
        row = self.table.currentRow()
        if self.busy or not 0 <= row < len(self.scores):
            return
        score = self.scores[row]
        cached = all((score_folder(score) / name).is_file() for name in ("score.mid", "source.json"))
        if not cached and (not score.pdf_url or not score.midi_url or (score.provider == "ichigos" and not self.personal_use.isChecked())):
            return
        personal_use = self.personal_use.isChecked()
        self._set_busy(True)
        self.status.setText("Downloading PDF and MIDI…")

        def worker():
            try:
                folder = download_score(score, personal_use=personal_use)
                self.download_ready.emit((score, folder))
            except Exception as exc:
                self.network_error.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _download_done(self, payload):
        self._set_busy(False)
        score, folder = payload
        try:
            self.practice.open_score(score, folder)
        except ValueError as exc:
            self._error(str(exc))
            return
        self.score_available.emit((score, folder))
        if self._external_practice:
            self.practice_requested.emit()
        else:
            self.setCurrentWidget(self.practice)
        self.status.setText("Download complete. The score is saved for offline practice.")

    def _error(self, message):
        self._set_busy(False)
        self.status.setText("Online score unavailable. You can still open downloaded scores.\n" + message)

    def open_import(self):
        provider = self.provider.currentData()
        self.musescore.set_source(provider if provider != "mutopia" else "musescore", self.query.text())
        self.setCurrentWidget(self.musescore)

    def open_policy(self):
        QDesktopServices.openUrl(QUrl(POLICY_URLS[self.provider.currentData()]))

    def open_source(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.scores):
            score = self.scores[row]
            try:
                checked_url(score.source_url, score.provider)
            except ValueError as exc:
                self._error(str(exc))
                return
            QDesktopServices.openUrl(QUrl(score.source_url))
