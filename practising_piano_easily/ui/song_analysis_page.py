"""MIDI import workflow with editable chord confirmation and score-labelled candidates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QHBoxLayout, QSpinBox, QSplitter, QVBoxLayout, QWidget)
from .localized_widgets import (QFileDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QTextEdit)

from practising_piano_easily.analysis import chord_candidates, key_candidates, load_midi, note_windows
from practising_piano_easily.core import analyze_progression, parse_key


class SongAnalysisPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.summary = None
        self.keys = ()
        layout = QVBoxLayout(self)
        title = QLabel("Song Analysis")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        row = QHBoxLayout()
        self.path = QLineEdit()
        browse = QPushButton("Browse…")
        load = QPushButton("Load MIDI")
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        row.addWidget(load)
        layout.addLayout(row)
        controls = QFormLayout()
        self.window_beats = QSpinBox()
        self.window_beats.setRange(1, 16)
        self.window_beats.setValue(1)
        controls.addRow("Segmentation window (beats):", self.window_beats)
        layout.addLayout(controls)
        splitter = QSplitter()
        self.events = QTextEdit()
        self.events.setReadOnly(True)
        self.candidates = QTextEdit()
        self.candidates.setReadOnly(True)
        splitter.addWidget(self.events)
        splitter.addWidget(self.candidates)
        layout.addWidget(splitter, 1)
        self.confirmed = QLineEdit()
        self.confirmed.setPlaceholderText("Confirm or edit chord symbols here")
        analyze = QPushButton("Analyze confirmed chords")
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Confirmed chords:"))
        bottom.addWidget(self.confirmed, 1)
        bottom.addWidget(analyze)
        layout.addLayout(bottom)
        self.harmony = QTextEdit()
        self.harmony.setReadOnly(True)
        self.harmony.setMaximumHeight(190)
        layout.addWidget(self.harmony)

        browse.clicked.connect(self._browse)
        load.clicked.connect(self.load_path)
        self.window_beats.valueChanged.connect(self._render_analysis)
        analyze.clicked.connect(self._analyze_confirmed)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open MIDI", str(Path.home()), "MIDI files (*.mid *.midi)")
        if path:
            self.path.setText(path)
            self.load_path()

    def load_path(self) -> None:
        try:
            self.summary = load_midi(self.path.text())
        except ValueError as exc:
            self.events.setPlainText(str(exc))
            self.candidates.clear()
            self.harmony.clear()
            return
        self._render_analysis()

    def _render_analysis(self) -> None:
        if self.summary is None:
            return
        summary = self.summary
        note_range = f"{summary.note_range[0]}–{summary.note_range[1]}" if summary.note_range else "—"
        header = (
            f"Tracks: {summary.tracks}\nTempo: {summary.tempo_bpm:.1f} BPM\n"
            f"Time signature: {summary.time_signature}\nTicks per beat: {summary.ticks_per_beat}\n"
            f"Note events: {len(summary.notes)}\nRange: {note_range}\nDuration: {summary.duration_ticks} ticks\n\n"
        )
        event_lines = [
            f"t={note.start_tick}–{note.end_tick}  track={note.track}  note={note.note}  vel={note.velocity}"
            for note in summary.notes[:200]
        ]
        self.events.setPlainText(header + "Note events / piano-roll summary:\n" + "\n".join(event_lines))
        windows = note_windows(summary, summary.ticks_per_beat * self.window_beats.value())
        lines = ["Chord candidates (heuristic Score, not Probability):"]
        confirmed = []
        for index, notes in enumerate(windows, start=1):
            choices = chord_candidates(notes)
            if not choices:
                lines.append(f"Window {index}: rest")
                continue
            confirmed.append(choices[0].symbol)
            lines.append(f"Window {index}: " + ", ".join(f"{item.symbol} [{item.score:.3f}]" for item in choices))
        pitch_classes = {note.note % 12 for note in summary.notes}
        self.keys = key_candidates(pitch_classes)
        lines.extend(("", "Key candidates (Score, not Probability):"))
        lines.extend(f"{item.key}: {item.score:.3f}" for item in self.keys)
        self.candidates.setPlainText("\n".join(lines))
        self.confirmed.setText(" ".join(confirmed))
        self._analyze_confirmed()

    def _analyze_confirmed(self) -> None:
        if not self.keys:
            self.harmony.setPlainText("Load a MIDI file first.")
            return
        try:
            key = parse_key(self.keys[0].key)
            findings = analyze_progression(self.confirmed.text().split(), key)
        except ValueError as exc:
            self.harmony.setPlainText(f"Invalid confirmed chord: {exc}")
            return
        lines = [f"User-confirmed analysis in candidate key {key.name}:"]
        for item in findings:
            lines.append(f"{item.chord_symbol}: {item.roman or 'unclassified'} ({'chromatic' if item.chromatic else 'diatonic'})")
            lines.extend(f"  Possible interpretation: {text}" for text in item.possible_interpretations)
        self.harmony.setPlainText("\n".join(lines))
