"""Small Qt display adapters. canonicalText() is the stable combo value, never its translation."""

from PySide6 import QtWidgets as Qt
from PySide6.QtCore import QSignalBlocker, Qt as QtCore

from .i18n import language, tr


class TextMixin:
    def __init__(self, text="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_text = text
        language.changed.connect(self.retranslate)
        self.retranslate()

    def setText(self, text):
        self.source_text = text
        super().setText(tr(text))

    def clear(self):
        self.setText("")

    def retranslate(self):
        super().setText(tr(self.source_text))


class QLabel(TextMixin, Qt.QLabel):
    pass


class QPushButton(TextMixin, Qt.QPushButton):
    pass


class QCheckBox(TextMixin, Qt.QCheckBox):
    pass


class QComboBox(Qt.QComboBox):
    SOURCE_ROLE = QtCore.ItemDataRole.UserRole + 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language.changed.connect(self.retranslate)

    def addItem(self, text, userData=None):
        super().addItem(tr(text), userData)
        self.setItemData(self.count() - 1, text, self.SOURCE_ROLE)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def canonicalText(self):
        return self.currentData(self.SOURCE_ROLE) or ""

    def setCanonicalText(self, text):
        index = self.findData(text, self.SOURCE_ROLE)
        if index >= 0:
            self.setCurrentIndex(index)

    def retranslate(self):
        # Display changes must not generate new questions or save translated IDs.
        with QSignalBlocker(self):
            for index in range(self.count()):
                self.setItemText(index, tr(self.itemData(index, self.SOURCE_ROLE) or ""))


class QFormLayout(Qt.QFormLayout):
    def addRow(self, *args):
        if len(args) == 2 and isinstance(args[0], str):
            args = (QLabel(args[0]), args[1])
        super().addRow(*args)


class QListWidget(Qt.QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language.changed.connect(self.retranslate)

    def addItems(self, texts):
        for text in texts:
            item = Qt.QListWidgetItem(tr(text))
            item.setData(QtCore.ItemDataRole.UserRole, text)
            self.addItem(item)

    def retranslate(self):
        for index in range(self.count()):
            item = self.item(index)
            item.setText(tr(item.data(QtCore.ItemDataRole.UserRole)))


class QTabWidget(Qt.QTabWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._titles = []
        language.changed.connect(self.retranslate)

    def addTab(self, page, text):
        self._titles.append(text)
        return super().addTab(page, tr(text))

    def retranslate(self):
        for index, title in enumerate(self._titles):
            self.setTabText(index, tr(title))


class QTableWidget(Qt.QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._headers = []
        language.changed.connect(self.retranslate)

    def setHorizontalHeaderLabels(self, texts):
        self._headers = list(texts)
        self.retranslate()

    def retranslate(self):
        super().setHorizontalHeaderLabels([tr(text) for text in self._headers])


class QTextEdit(Qt.QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_text = ""
        language.changed.connect(self.retranslate)

    def setPlainText(self, text):
        self.source_text = text
        super().setPlainText(tr(text) if self.isReadOnly() else text)

    def clear(self):
        self.setPlainText("")

    def retranslate(self):
        if self.isReadOnly():
            scroll = self.verticalScrollBar().value()
            super().setPlainText(tr(self.source_text))
            self.verticalScrollBar().setValue(scroll)


class QLineEdit(Qt.QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._placeholder = ""
        language.changed.connect(self.retranslate)

    def setPlaceholderText(self, text):
        self._placeholder = text
        self.retranslate()

    def retranslate(self):
        super().setPlaceholderText(tr(self._placeholder))


class QMessageBox(Qt.QMessageBox):
    @staticmethod
    def information(parent, title, text):
        return Qt.QMessageBox.information(parent, tr(title), tr(text))

    @staticmethod
    def critical(parent, title, text):
        return Qt.QMessageBox.critical(parent, tr(title), tr(text))


class QFileDialog(Qt.QFileDialog):
    @staticmethod
    def getOpenFileName(parent, caption, directory, filter):
        return Qt.QFileDialog.getOpenFileName(parent, tr(caption), directory, tr(filter))

    @staticmethod
    def getSaveFileName(parent, caption, directory, filter):
        return Qt.QFileDialog.getSaveFileName(parent, tr(caption), directory, tr(filter))
