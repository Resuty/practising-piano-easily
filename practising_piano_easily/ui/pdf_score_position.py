"""Locate the opening staff without changing the source PDF or recognizing notes."""

import numpy as np
from PySide6.QtCore import QSizeF, Qt
from PySide6.QtGui import QImage, QPainter


def first_staff_top(document):
    """Return a page-0 Y coordinate, leaving space above the first five staff lines."""
    page = document.pagePointSize(0)
    if page.isEmpty():
        return 0.0
    size = page.scaled(QSizeF(800, 1600), Qt.AspectRatioMode.KeepAspectRatio).toSize()
    image = document.render(0, size)
    if image.isNull():
        return 0.0
    # QtPdf renders transparent paper; composite onto white before finding dark lines.
    paper = QImage(image.size(), QImage.Format.Format_RGB32)
    paper.fill(Qt.GlobalColor.white)
    painter = QPainter(paper)
    painter.drawImage(0, 0, image)
    painter.end()
    gray = paper.convertToFormat(QImage.Format.Format_Grayscale8)
    pixels = np.frombuffer(gray.constBits(), dtype=np.uint8).reshape(gray.height(), gray.bytesPerLine())[:, :gray.width()]
    rows = np.flatnonzero((pixels[:, gray.width() // 10:gray.width() * 9 // 10] < 180).mean(axis=1) > 0.45)
    if not len(rows):
        return 0.0
    lines = rows[np.r_[True, np.diff(rows) > 1]]
    # shortcut: five long, evenly spaced lines locate the opening system, not individual measures or MIDI notes.
    for index in range(len(lines) - 4):
        gaps = np.diff(lines[index:index + 5])
        if gaps.min() >= 2 and gaps.max() <= 16 and np.ptp(gaps) <= 2:
            return max(0, int(lines[index]) - 42) * page.height() / gray.height()
    return 0.0
