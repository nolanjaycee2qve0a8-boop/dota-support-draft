import sys

from dota_support_draft.ui import create_main_window


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as error:
        message = "PySide6 is required for the desktop shell. Install project dependencies first."
        raise RuntimeError(message) from error
    application = QApplication(sys.argv)
    window = create_main_window()
    window.show()  # type: ignore[attr-defined]
    return int(application.exec())
