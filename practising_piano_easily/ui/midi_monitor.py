"""MIDI connection controls and raw-event monitor."""

from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget)
from .localized_widgets import (QComboBox, QLabel, QPushButton, QTableWidget)

from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.trainers.chord_construction import midi_note_name


class MidiMonitorPage(QWidget):
    def __init__(self, controller: MidiController) -> None:
        super().__init__()
        self.controller = controller
        self.notation_preference = "Context"
        layout = QVBoxLayout(self)
        title = QLabel("MIDI Monitor")
        title.setStyleSheet("font-size: 28px; font-weight: 700")
        layout.addWidget(title)
        row = QHBoxLayout()
        self.devices = QComboBox()
        connect = QPushButton("Connect")
        refresh = QPushButton("Refresh")
        row.addWidget(QLabel("Input:"))
        row.addWidget(self.devices, 1)
        row.addWidget(connect)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.status = QLabel("Not connected")
        self.pedal = QLabel("Sustain: up")
        layout.addWidget(self.status)
        layout.addWidget(self.pedal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Event", "Note", "Name", "Velocity / Value", "CC"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        connect.clicked.connect(lambda: controller.connect_device(self.devices.canonicalText()))
        refresh.clicked.connect(controller.refresh_devices)
        controller.devices_ready.connect(self._set_devices)
        controller.status_changed.connect(self.status.setText)
        controller.event_received.connect(self._append_event)

    def _set_devices(self, names: list[str]) -> None:
        previous = self.devices.canonicalText()
        self.devices.clear()
        self.devices.addItems(names)
        if previous in names:
            self.devices.setCanonicalText(previous)
        if not names:
            self.status.setText("No MIDI input found. Connect the keyboard, then click Refresh.")
        elif len(names) == 1:
            self.controller.connect_device(names[0])
        else:
            self.status.setText("Choose a MIDI input, then click Connect.")

    def _append_event(self, payload: dict) -> None:
        event = payload["event"]
        row = 0
        self.table.insertRow(row)
        values = (
            payload["timestamp"].split("T")[-1],
            event.event_type,
            "" if event.note is None else str(event.note),
            "" if event.note is None else midi_note_name(event.note, preference=self.notation_preference),
            str(event.velocity if event.note is not None else event.value),
            "" if event.control is None else str(event.control),
        )
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(value))
        self.pedal.setText("Sustain: down" if payload["pedal"] else "Sustain: up")
        while self.table.rowCount() > 300:
            self.table.removeRow(self.table.rowCount() - 1)
