def create_main_window() -> object:
    """Create the small PySide6 shell while keeping non-GUI imports dependency-light."""
    from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

    window = QMainWindow()
    window.setWindowTitle("Dota Support Draft Assistant")
    contents = QWidget()
    layout = QVBoxLayout(contents)
    layout.addWidget(QLabel("Dota Support Draft Assistant"))
    layout.addWidget(QLabel("Ready"))
    window.setCentralWidget(contents)
    window.resize(420, 160)
    return window
