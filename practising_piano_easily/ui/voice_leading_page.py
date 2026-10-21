"""Compare entered MIDI voicings using objective movement metrics."""

from __future__ import annotations

from PySide6.QtWidgets import (QVBoxLayout, QWidget)
from .localized_widgets import (QLabel, QPushButton, QTextEdit)

from practising_piano_easily.core import measure_progression


class VoiceLeadingPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Voice Leading")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        layout.addWidget(QLabel("Enter one MIDI-note voicing per line. This page reports measurements, not quality judgments."))
        self.input = QTextEdit()
        self.input.setPlainText("50 53 57 60\n50 53 55 59\n48 52 55 59")
        self.input.setMaximumHeight(140)
        layout.addWidget(self.input)
        analyze = QPushButton("Measure")
        analyze.clicked.connect(self._analyze)
        layout.addWidget(analyze)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self._analyze()

    def _analyze(self) -> None:
        try:
            voicings = [tuple(map(int, line.split())) for line in self.input.toPlainText().splitlines() if line.strip()]
            if any(any(note < 0 or note > 127 for note in voicing) for voicing in voicings):
                raise ValueError("MIDI notes must be between 0 and 127")
            metrics = measure_progression(voicings)
        except ValueError as exc:
            self.output.setPlainText(f"Invalid voicing: {exc}")
            return
        if not metrics:
            self.output.setPlainText("Enter at least two non-empty voicings.")
            return
        lines = []
        for index, item in enumerate(metrics, start=1):
            lines.extend((
                f"Transition {index} → {index + 1}",
                f"  Total movement: {item.total_movement} semitones",
                f"  Largest leap: {item.largest_leap} semitones",
                f"  Common tones retained: {item.common_tones_retained}",
            ))
        lines.append("")
        lines.append(f"Progression total movement: {sum(item.total_movement for item in metrics)} semitones")
        self.output.setPlainText("\n".join(lines))
