"""Table-based progression editor with voicing analysis and MIDI export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QHBoxLayout, QSpinBox, QTableWidgetItem, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QFileDialog, QLabel, QMessageBox, QPushButton, QTableWidget, QTextEdit)

from practising_piano_easily.composition import Progression, ProgressionChord, analyze_composition, export_midi
from practising_piano_easily.core import parse_chord, parse_key

from .harmony_page import KEYS


class CompositionPage(QWidget):
    COLUMNS = ("Chord", "Beats", "Inversion", "Octave", "Velocity")

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Composition Lab")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        top = QHBoxLayout()
        self.key = QComboBox()
        self.key.addItems(KEYS)
        self.tempo = QSpinBox()
        self.tempo.setRange(20, 300)
        self.tempo.setValue(120)
        top.addWidget(QLabel("Analysis key:"))
        top.addWidget(self.key)
        top.addWidget(QLabel("Tempo:"))
        top.addWidget(self.tempo)
        top.addStretch()
        layout.addLayout(top)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        for symbol in ("Cmaj7", "A7", "Dm7", "G7"):
            self._add_row(symbol)
        buttons = QHBoxLayout()
        for label, action in (
            ("Add", self._add_row), ("Delete", self._delete_row),
            ("Move up", lambda: self._move_row(-1)), ("Move down", lambda: self._move_row(1)),
            ("Analyze", self._analyze), ("Export MIDI…", self._export),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self._analyze()

    def _add_row(self, symbol: str | bool = "C") -> None:
        if isinstance(symbol, bool):
            symbol = "C"
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate((symbol, "4", "0", "3", "80")):
            self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.setCurrentCell(row, 0)

    def _delete_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _move_row(self, offset: int) -> None:
        row = self.table.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        values = [[self.table.item(index, column).text() for column in range(len(self.COLUMNS))]
                  for index in (row, target)]
        for column in range(len(self.COLUMNS)):
            self.table.item(row, column).setText(values[1][column])
            self.table.item(target, column).setText(values[0][column])
        self.table.setCurrentCell(target, 0)

    def progression(self) -> Progression:
        chords = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, column).text().strip() for column in range(len(self.COLUMNS))]
            chords.append(ProgressionChord(
                symbol=parse_chord(values[0]).symbol,
                duration_beats=float(values[1]), inversion=int(values[2]),
                octave=int(values[3]), velocity=int(values[4]),
            ))
        return Progression(chords)

    def _analyze(self) -> None:
        try:
            progression = self.progression()
            report = analyze_composition(progression, parse_key(self.key.canonicalText()))
        except (ValueError, AttributeError) as exc:
            self.output.setPlainText(f"Invalid progression: {exc}")
            return
        lines = [f"Key candidate: {self.key.canonicalText()}", ""]
        for index, (item, finding, voicing) in enumerate(zip(progression.chords, report.harmony, report.voicings), start=1):
            chord = parse_chord(item.symbol)
            lines.append(
                f"{index}. {chord.symbol}  |  {finding.roman or 'unclassified'}  |  "
                f"{'chromatic' if finding.chromatic else 'diatonic'}"
            )
            lines.append(f"   Tones: {' '.join(map(str, chord.notes))}  |  Bass: {chord.bass or chord.root}")
            lines.append(f"   Voicing: {' '.join(map(str, voicing))}")
            lines.extend(f"   Possible interpretation: {text}" for text in finding.possible_interpretations)
            if index > 1:
                metrics = report.voice_leading[index - 2]
                lines.append(
                    f"   From previous: movement {metrics.total_movement}, largest leap {metrics.largest_leap}, "
                    f"common tones {metrics.common_tones_retained}"
                )
        self.output.setPlainText("\n".join(lines))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export progression MIDI", str(Path.cwd() / "exports" / "progression.mid"), "MIDI files (*.mid)"
        )
        if not path:
            return
        try:
            saved = export_midi(self.progression(), path, self.tempo.value())
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "MIDI export failed", str(exc))
            return
        QMessageBox.information(self, "MIDI export", f"Saved to:\n{saved}")
