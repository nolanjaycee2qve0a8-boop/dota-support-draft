from datetime import date

from PySide6.QtCore import QPoint, QRect, QThread
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from dota_support_draft.domain import Hero, Patch
from dota_support_draft.draft import ManualDraftSession
from dota_support_draft.ui.main_window import create_main_window


def _button(window, name: str) -> QPushButton:
    button = window.findChild(QPushButton, name)
    assert button is not None
    return button


def _viewport_rect(scroll: QScrollArea) -> QRect:
    viewport = scroll.viewport()
    return QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())


def _assert_in_viewport(scroll: QScrollArea, widget: QWidget) -> None:
    """Require a complete control rectangle to be visible to a compact-window user."""
    widget_rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
    assert _viewport_rect(scroll).contains(widget_rect)


def _scroll_to_control(scroll: QScrollArea, widget: QWidget) -> None:
    """Prove ordinary scrollbar movement can reach one dense local-only control."""
    content = scroll.widget()
    assert content is not None
    target_y = widget.mapTo(content, QPoint(0, 0)).y()
    scroll.verticalScrollBar().setValue(
        min(max(target_y - 12, 0), scroll.verticalScrollBar().maximum())
    )
    QApplication.processEvents()
    _assert_in_viewport(scroll, widget)


def test_compact_layout_reveals_expanded_sections_and_preserves_local_only_contract() -> None:
    """Accordion expansion reveals its primary action without pair dispatch or worker creation."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    window = create_main_window(ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1))))
    window.resize(2559, 664)
    window.show()
    app.processEvents()

    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    splitter = window.findChild(QSplitter, "draft-content-splitter")
    import_section = window.findChild(QWidget, "manual-import-section")
    snapshot_section = window.findChild(QWidget, "local-snapshot-section")
    import_text = window.findChild(QTextEdit, "manual-import-text")
    validate_import = window.findChild(QPushButton, "validate-manual-import")
    snapshot_name = window.findChild(QLineEdit, "local-snapshot-name")
    save_snapshot = window.findChild(QPushButton, "save-local-snapshot")
    assert (
        scroll is not None
        and splitter is not None
        and import_section is not None
        and snapshot_section is not None
        and import_text is not None
        and validate_import is not None
        and snapshot_name is not None
        and save_snapshot is not None
    )
    assert window.pair_refresh_controller is None and window.findChildren(QThread) == []

    _button(window, "toggle-manual-import").click()
    app.processEvents()
    assert import_section.isVisible() and not snapshot_section.isVisible()
    _assert_in_viewport(scroll, import_text)
    _assert_in_viewport(scroll, validate_import)
    import_text.setFocus()
    assert import_text.hasFocus()

    _button(window, "toggle-local-snapshots").click()
    app.processEvents()
    assert snapshot_section.isVisible() and not import_section.isVisible()
    assert _button(window, "toggle-manual-import").text() == "Show import"
    _assert_in_viewport(scroll, snapshot_name)
    _assert_in_viewport(scroll, save_snapshot)

    _button(window, "toggle-local-snapshots").click()
    app.processEvents()
    assert not snapshot_section.isVisible() and splitter.sizes()[1] == 0
    assert window.pair_refresh_controller is None and window.findChildren(QThread) == []
    window.close()


def test_compact_layout_scroll_reaches_recovery_composition_and_candidate_regions_locally() -> None:
    """Scrolling/focus changes expose each dense region without changing draft or pair state."""
    app = QApplication.instance() or QApplication([])
    heroes = tuple(Hero(index, f"hero_{index}") for index in range(1, 4))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    before = session.to_draft_state()
    window = create_main_window(session)
    window.resize(2559, 664)
    window.show()
    app.processEvents()

    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    widgets = (
        window.findChild(QWidget, "session-recovery-status"),
        window.findChild(QComboBox, "ally-team-position"),
        window.findChild(QComboBox, "ally-planned-lane"),
        window.findChild(QLineEdit, "candidate-search"),
        window.findChild(QTableWidget, "candidate-table"),
        window.findChild(QTextEdit, "recommendation-explanation"),
        window.findChild(QWidget, "candidate-comparison"),
    )
    assert scroll is not None and all(widget is not None for widget in widgets)
    assert scroll.verticalScrollBar().maximum() > 0
    for widget in widgets:
        assert widget is not None
        _scroll_to_control(scroll, widget)

    search = window.findChild(QLineEdit, "candidate-search")
    assert search is not None
    search.setText("hero")
    app.processEvents()
    assert session.to_draft_state() == before
    assert window.pair_refresh_controller is None and window.findChildren(QThread) == []
    window.close()
