"""Persisted settings with immediate application to active trainers."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QSpinBox, QVBoxLayout, QWidget)
from .localized_widgets import (QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton)


DEFAULTS = {
    "midi_input": "", "midi_output": "", "audio_output": "",
    "settling_ms": "300", "octaves": "3", "notation": "Context",
    "ear_volume": "25", "question_count": "20", "difficulty": "1",
    "curriculum_stage": "1", "midi_debug": "0", "language": "zh_CN",
}


class SettingsPage(QWidget):
    settings_saved = Signal(object)

    def __init__(self, database, controller) -> None:
        super().__init__()
        self.database = database
        self.controller = controller
        layout = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        form = QFormLayout()
        self.language = QComboBox()
        self.language.addItem("简体中文", "zh_CN")
        self.language.addItem("English", "en")
        self.language.addItem("日本語", "ja")
        self.midi_input = QComboBox()
        self.midi_output = QLineEdit()
        self.audio_output = QComboBox()
        self.audio_output.addItem("System default", "")
        try:
            import sounddevice

            for index, device in enumerate(sounddevice.query_devices()):
                if device["max_output_channels"] > 0:
                    self.audio_output.addItem(f"{index}: {device['name']}", str(index))
        except Exception:
            pass
        self.settling = QSpinBox(); self.settling.setRange(150, 800); self.settling.setSuffix(" ms")
        self.octaves = QSpinBox(); self.octaves.setRange(3, 5)
        self.notation = QComboBox(); self.notation.addItems(["Context", "Prefer sharps", "Prefer flats"])
        self.volume = QSpinBox(); self.volume.setRange(0, 100); self.volume.setSuffix("%")
        self.questions = QSpinBox(); self.questions.setRange(5, 100)
        self.difficulty = QSpinBox(); self.difficulty.setRange(1, 8)
        self.stage = QSpinBox(); self.stage.setRange(1, 10)
        self.midi_debug = QCheckBox("Log raw MIDI events at DEBUG level")
        for label, widget in (
            ("Language / 语言", self.language),
            ("MIDI input:", self.midi_input), ("MIDI output (optional):", self.midi_output),
            ("Audio output:", self.audio_output), ("Chord settling:", self.settling),
            ("Keyboard octaves:", self.octaves), ("Contextless notation:", self.notation),
            ("Ear-training volume:", self.volume), ("Question count:", self.questions),
            ("Difficulty / chord level:", self.difficulty), ("Curriculum stage:", self.stage),
            ("MIDI logging:", self.midi_debug),
        ):
            form.addRow(label, widget)
        layout.addLayout(form)
        save = QPushButton("Save settings")
        save.clicked.connect(self.save)
        layout.addWidget(save)
        layout.addStretch()
        controller.devices_ready.connect(self._set_devices)
        self._load()

    def _load(self) -> None:
        values = {key: self.database.get_setting(key, default) for key, default in DEFAULTS.items()}
        self.language.setCurrentIndex(max(0, self.language.findData(values["language"])))
        self.midi_output.setText(values["midi_output"])
        self.settling.setValue(int(values["settling_ms"]))
        self.octaves.setValue(int(values["octaves"]))
        self.notation.setCanonicalText(values["notation"])
        self.volume.setValue(int(values["ear_volume"]))
        self.questions.setValue(int(values["question_count"]))
        self.difficulty.setValue(int(values["difficulty"]))
        self.stage.setValue(int(values["curriculum_stage"]))
        self.midi_debug.setChecked(values["midi_debug"] == "1")
        index = self.audio_output.findData(values["audio_output"])
        self.audio_output.setCurrentIndex(max(0, index))

    def _set_devices(self, names: list[str]) -> None:
        saved = self.database.get_setting("midi_input", "")
        self.midi_input.clear()
        self.midi_input.addItem("Not selected", "")
        for name in names:
            self.midi_input.addItem(name, name)
        index = self.midi_input.findData(saved)
        self.midi_input.setCurrentIndex(max(0, index))

    def values(self) -> dict[str, str]:
        return {
            "language": self.language.currentData() or "zh_CN",
            "midi_input": self.midi_input.currentData() or "",
            "midi_output": self.midi_output.text().strip(),
            "audio_output": self.audio_output.currentData() or "",
            "settling_ms": str(self.settling.value()), "octaves": str(self.octaves.value()),
            "notation": self.notation.canonicalText(), "ear_volume": str(self.volume.value()),
            "question_count": str(self.questions.value()), "difficulty": str(self.difficulty.value()),
            "curriculum_stage": str(self.stage.value()), "midi_debug": "1" if self.midi_debug.isChecked() else "0",
        }

    def save(self) -> None:
        values = self.values()
        try:
            self.database.set_settings(values)
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Database error", f"Settings were not fully saved.\n\n{exc}")
            return
        if values["midi_input"]:
            self.controller.connect_device(values["midi_input"])
        logging.getLogger("practising_piano_easily.midi.controller").setLevel(
            logging.DEBUG if values["midi_debug"] == "1" else logging.INFO
        )
        self.settings_saved.emit(values)
