"""Shared notation controls; each practice workspace keeps its own saved preferences."""

import sqlite3

from PySide6.QtWidgets import QHBoxLayout, QSpinBox, QWidget

from .localized_widgets import QComboBox, QLabel


class NotationControls(QWidget):
    def __init__(self, notation, database, prefix):
        super().__init__()
        self.notation, self.database, self.prefix = notation, database, prefix
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Score zoom:"))
        self.zoom = QSpinBox()
        self.zoom.setRange(50, 200)
        self.zoom.setSingleStep(10)
        self.zoom.setSuffix("%")
        self.zoom.setValue(self._stored_int("zoom", 100, 50, 200))
        layout.addWidget(self.zoom)
        layout.addWidget(QLabel("Bars per line:"))
        self.bars = QComboBox()
        self.bars.addItem("Automatic", 0)
        for count in range(1, 9):
            self.bars.addItem(str(count), count)
        self.bars.setCurrentIndex(self._stored_int("bars", 0, 0, 8))
        layout.addWidget(self.bars)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.hide()
        layout.addWidget(self.warning, 1)
        layout.addStretch()
        self._saved_options = self.values()
        notation.set_layout_options(*self.values())
        self.zoom.valueChanged.connect(self._changed)
        self.bars.currentIndexChanged.connect(self._changed)

    def _stored_int(self, suffix, default, low, high):
        try:
            value = int(self.database.get_setting(f"{self.prefix}_{suffix}", str(default)))
        except (TypeError, ValueError):
            return default
        return value if low <= value <= high else default

    def values(self):
        return self.zoom.value(), self.bars.currentData()

    def _changed(self):
        self.notation.set_layout_options(*self.values())
        self.save_options()

    def save_options(self):
        values = self.values()
        if values == self._saved_options:
            self.warning.hide()
            return
        try:
            self.database.set_settings({f"{self.prefix}_zoom": str(values[0]), f"{self.prefix}_bars": str(values[1])})
            self._saved_options = values
            self.warning.hide()
        except sqlite3.Error:
            self.warning.setText("Score settings could not be saved. Current choices still apply; leaving or closing will retry.")
            self.warning.show()

    def hideEvent(self, event):
        self.save_options()
        super().hideEvent(event)
