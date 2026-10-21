"""Application entry point."""

import logging
import sys
from pathlib import Path

from .paths import data_directory, database_path


def scan_midi(output: Path) -> int:
    """A windowless EXE has no stdout; return discovery results through a file."""
    import json

    try:
        import mido
        output.write_text(json.dumps(mido.get_input_names(), ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception as exc:
        output.write_text(json.dumps({"error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        return 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--midi-scan":
        return scan_midi(Path(sys.argv[2]))
    if getattr(sys, "frozen", False):
        try:
            data_directory().mkdir(parents=True, exist_ok=True)
            logging.basicConfig(filename=data_directory() / "application.log", encoding="utf-8",
                                level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        except OSError:
            logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QFont
    from .ui.main_window import MainWindow
    from .storage import Database

    application = QApplication(sys.argv)
    application.setApplicationName("practising piano easily")
    application.setStyle("Fusion")
    if sys.platform == "win32":
        application.setFont(QFont("Microsoft YaHei UI", 10))
    try:
        database = Database(database_path())
        if getattr(sys, "frozen", False) and not database.get_setting("language", ""):
            database.set_setting("language", "ja")
        window = MainWindow(database)
    except Exception as exc:
        logging.exception("Application startup failed")
        QMessageBox.critical(None, "practising piano easily", f"The application could not start.\n\n{exc}")
        return 1
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
