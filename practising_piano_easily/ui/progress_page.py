"""All-time dashboard, error analysis, mastery, and portable export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget)
from .localized_widgets import (QFileDialog, QLabel, QMessageBox, QPushButton, QTextEdit)

from practising_piano_easily.progress import dashboard_report, export_attempts_csv, export_attempts_json


class ProgressPage(QWidget):
    def __init__(self, database) -> None:
        super().__init__()
        self.database = database
        layout = QVBoxLayout(self)
        title = QLabel("Progress")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        explanation = QLabel("Practice fluency uses accuracy and consecutive successes. Hints are allowed; speed and next-day tests are not required.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        csv_button = QPushButton("Export CSV…")
        json_button = QPushButton("Export JSON…")
        buttons.addWidget(refresh)
        buttons.addWidget(csv_button)
        buttons.addWidget(json_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        refresh.clicked.connect(self.refresh)
        csv_button.clicked.connect(lambda: self._export("csv"))
        json_button.clicked.connect(lambda: self._export("json"))
        self.refresh()

    def refresh(self) -> None:
        report = dashboard_report(self.database)
        lines = [
            f"Overall practice time: {report['practice_seconds'] // 60} min",
            f"Sessions: {report['sessions']}", f"Attempts: {report['attempts']}",
            f"Accuracy: {report['accuracy']:.1f}%",
            f"Average response: {report['average_response_ms'] / 1000:.2f} s",
            f"Practice volume: last 7 days {report['last_7_days']} · last 30 days {report['last_30_days']}",
            "", "Chord-quality accuracy:",
        ]
        lines.extend(f"  {name}: {value:.1f}%" for name, value in sorted(report["quality_accuracy"].items()))
        lines.extend(("", "Root accuracy:"))
        lines.extend(f"  {name}: {value:.1f}%" for name, value in sorted(report["root_accuracy"].items()))
        lines.extend(("", "Skill accuracy:"))
        lines.extend(f"  {name}: {value:.1f}%" for name, value in sorted(report["skill_accuracy"].items()))
        lines.extend(("", "Mastery:"))
        lines.extend(f"  {name}: {value}" for name, value in sorted(report["mastery"].items()))
        lines.extend(("", "Common confusions:"))
        lines.extend(f"  {name}: {count}" for name, count in report["confusions"])
        if not report["confusions"]:
            lines.append("  —")
        self.output.setPlainText("\n".join(lines))

    def _export(self, kind: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {kind.upper()}", str(Path.cwd() / "exports" / f"attempts.{kind}"),
            f"{kind.upper()} files (*.{kind})",
        )
        if not path:
            return
        try:
            saved = export_attempts_csv(self.database, path) if kind == "csv" else export_attempts_json(self.database, path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export", f"Saved to:\n{saved}")
