"""Browser discovery and permitted local-file handoff for external score sites."""

from pathlib import Path

from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout

from practising_piano_easily.analysis.online_scores import (musescore_search_url, import_musescore_score, import_score_files,
                                                       SOURCE_NAMES, POLICY_URLS, MAX_BYTES)
from practising_piano_easily.analysis.fan_scores import fan_search_url
from .localized_widgets import QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QComboBox


class MuseScorePage(QWidget):
    imported = Signal(object)

    def __init__(self):
        super().__init__()
        self.midi_path = None
        self.pdf_path = None
        layout = QVBoxLayout(self)
        heading = QLabel("Import MIDI · optional PDF")
        heading.setStyleSheet("font-size: 24px; font-weight: 700")
        layout.addWidget(heading)
        info = QLabel("Search the selected score site in your browser. Check instrumentation, difficulty, credits and personal-use permission. Downloads may require a browser account or security check; this app does not bypass those requirements.")
        info.setWordWrap(True)
        layout.addWidget(info)
        search_row = QHBoxLayout()
        self.source_provider = QComboBox()
        for provider in ("local", "musescore", "ichigos", "ninsheetmusic"):
            self.source_provider.addItem(SOURCE_NAMES[provider], provider)
        search_row.addWidget(self.source_provider)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Song title + easy piano / beginner piano")
        search = self.search_button = QPushButton("Search selected site in browser")
        search.clicked.connect(self.open_search)
        self.query.returnPressed.connect(self.open_search)
        search_row.addWidget(self.query, 1)
        search_row.addWidget(search)
        layout.addLayout(search_row)
        self.source_hint = QLabel()
        self.source_hint.setWordWrap(True)
        layout.addWidget(self.source_hint)
        self.open_scores = QWidget()
        sources = QHBoxLayout(self.open_scores)
        sources.setContentsMargins(0, 0, 0, 0)
        for label, url in (("OpenScore · CC0 scores", "https://musescore.com/openscore"),
                           ("OpenScore Lieder · voice + piano", "https://musescore.com/openscore-lieder-corpus")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            sources.addWidget(button)
        layout.addWidget(self.open_scores)
        policy = self.policy_button = QPushButton("Read site usage and credits")
        policy.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(POLICY_URLS[self.source_provider.currentData()])))
        layout.addWidget(policy)
        steps = QLabel("1. Select a MIDI file; PDF is optional. Without PDF, the app generates a synchronized practice score.\n2. For a local file, select Local MIDI; no website link is required. For a website source, keep its original link and credits.\n3. Confirm personal-use permission and import. MSCZ/MusicXML must first be exported as MIDI; PDF alone cannot detect keys.")
        steps.setWordWrap(True)
        steps.setStyleSheet("padding: 12px; background: #eaf2f8; color: #172033")
        layout.addWidget(steps)
        form = QFormLayout()
        self.title_input = QLineEdit()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("https://musescore.com/.../scores/...")
        form.addRow(QLabel("Title"), self.title_input)
        form.addRow(QLabel("Original score-page link:"), self.source_input)
        self.arranger_input = QLineEdit()
        self.arranger_input.setPlaceholderText("Keep the original arranger's name and credits")
        form.addRow(QLabel("Composer / arranger:"), self.arranger_input)
        self.midi_button = QPushButton("Select MIDI…")
        self.midi_button.clicked.connect(self.choose_midi)
        self.pdf_button = QPushButton("Select PDF (optional)…")
        self.pdf_button.clicked.connect(self.choose_pdf)
        form.addRow(self.midi_button)
        pdf_row = QHBoxLayout()
        pdf_row.addWidget(self.pdf_button)
        self.clear_pdf = QPushButton("Remove PDF")
        self.clear_pdf.clicked.connect(self.remove_pdf)
        pdf_row.addWidget(self.clear_pdf)
        form.addRow(pdf_row)
        layout.addLayout(form)
        self.permission = QCheckBox("I have permission to use these files for personal practice. Import does not make them openly licensed.")
        layout.addWidget(self.permission)
        self.import_button = QPushButton("Import MIDI and practice")
        self.import_button.clicked.connect(self.import_files)
        layout.addWidget(self.import_button)
        self.status = QLabel("Imported copies stay on this computer; originals are not changed or uploaded.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()
        self.source_provider.currentIndexChanged.connect(self._source_changed)
        self._source_changed()

    def set_source(self, provider, query=""):
        self.source_provider.setCurrentIndex(self.source_provider.findData(provider))
        self.query.setText(query)

    def _source_changed(self):
        provider = self.source_provider.currentData()
        self.open_scores.setVisible(provider == "musescore")
        self.policy_button.setVisible(provider != "local")
        self.search_button.setEnabled(provider != "local")
        self.query.setEnabled(provider != "local")
        self.source_input.setEnabled(provider != "local")
        if provider == "local":
            self.source_hint.setText("Local MIDI works offline without a PDF or website link. Keep the original credits and use only files you have permission to practice.")
            placeholder = "No website link needed for local MIDI"
        elif provider == "ninsheetmusic":
            self.source_hint.setText("NinSheetMusic uses browser security checks. Search results open in your browser using a site-restricted web search. Download a matching PDF and MIDI there, then import below; this app does not bypass checks.")
            placeholder = "https://www.ninsheetmusic.org/browse/series/..."
        elif provider == "ichigos":
            self.source_hint.setText("Ichigo's: personal non-commercial use only. Keep all original credits and do not redistribute downloaded scores. Use the library tab for in-app search, or import a pair downloaded in your browser.")
            placeholder = "https://ichigos.com/sheets/..."
        else:
            self.source_hint.setText("MuseScore downloads follow each score's permissions. Use your browser account when required; restricted files are never fetched automatically.")
            placeholder = "https://musescore.com/.../scores/..."
        self.source_input.setPlaceholderText(placeholder)
        self.source_input.clear()
        self.title_input.clear()
        self.arranger_input.clear()
        self.permission.setChecked(False)
        self.midi_path = self.pdf_path = None
        self.midi_button.setText("Select MIDI…")
        self.remove_pdf()

    def open_search(self):
        provider = self.source_provider.currentData()
        if provider == "local":
            return
        url = musescore_search_url(self.query.text()) if provider == "musescore" else fan_search_url(provider, self.query.text())
        QDesktopServices.openUrl(QUrl(url))

    def choose_midi(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select MIDI", "", "MIDI files (*.mid *.midi)")
        if path:
            self.midi_path = Path(path)
            self.midi_button.setText(self.midi_path.name)
            if not self.title_input.text().strip():
                self.title_input.setText(self.midi_path.stem)

    def choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF files (*.pdf)")
        if path:
            self.pdf_path = Path(path)
            self.pdf_button.setText(self.pdf_path.name)
            self.clear_pdf.setEnabled(True)

    def remove_pdf(self):
        self.pdf_path = None
        self.pdf_button.setText("Select PDF (optional)…")
        self.clear_pdf.setEnabled(False)

    def import_files(self):
        if not self.midi_path:
            self.status.setText("Select a MIDI file first. PDF is optional.")
            return
        try:
            if self.pdf_path is not None:
                if self.pdf_path.stat().st_size > MAX_BYTES:
                    raise ValueError("Select MIDI and optional PDF files, each no larger than 15 MiB")
                document = QPdfDocument(self)
                error = document.load(str(self.pdf_path))
                valid = error == QPdfDocument.Error.None_ and document.pageCount() > 0
                document.close()
                document.deleteLater()
                if not valid:
                    raise ValueError("The selected PDF could not be opened")
            if self.source_provider.currentData() == "musescore":
                result = import_musescore_score(self.midi_path, self.pdf_path, self.title_input.text(),
                                                self.source_input.text(), self.permission.isChecked())
            else:
                result = import_score_files(self.midi_path, self.pdf_path, self.title_input.text(),
                                             self.source_input.text(), self.permission.isChecked(),
                                             provider=self.source_provider.currentData(), arranger=self.arranger_input.text())
        except (OSError, ValueError) as exc:
            self.status.setText("Import failed: " + str(exc))
            return
        self.status.setText("Imported. You can reopen this score from Downloaded scores without a network connection.")
        self.imported.emit(result)
