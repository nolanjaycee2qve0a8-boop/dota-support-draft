"""Offscreen regressions for local candidate-table readability and keyboard focus."""

from datetime import date

from PySide6.QtCore import QPoint, QRect, Qt, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from dota_support_draft.domain import Hero, Patch
from dota_support_draft.draft import ManualDraftSession, PairEvidenceResult
from dota_support_draft.ui.main_window import create_main_window


class CountingPairService:
    """A fake that makes unintended pair dispatch observable."""

    rank_bracket = None

    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, input_data):  # type: ignore[no-untyped-def]
        self.calls += 1
        return PairEvidenceResult(input_data.generation, input_data.context)


def _viewport_rect(scroll: QScrollArea) -> QRect:
    viewport = scroll.viewport()
    return QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())


def _scroll_to_control(scroll: QScrollArea, widget: QWidget) -> None:
    """Prove a compact window can reach a complete local display control."""
    contents = scroll.widget()
    assert contents is not None
    target_y = widget.mapTo(contents, QPoint(0, 0)).y()
    scroll.verticalScrollBar().setValue(
        min(max(target_y - 12, 0), scroll.verticalScrollBar().maximum())
    )
    QApplication.processEvents()
    widget_rect = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
    assert _viewport_rect(scroll).contains(widget_rect)


def _window_with_rows(service: CountingPairService | None = None):  # type: ignore[no-untyped-def]
    heroes = tuple(Hero(index, f"hero_{index}", f"Hero {index}") for index in range(1, 5))
    session = ManualDraftSession(heroes, Patch("p", "7.40", date(2026, 1, 1)))
    window = create_main_window(
        session,
        pair_service=service,  # type: ignore[arg-type]
        pair_debounce_ms=0,
    )
    return window, session


def test_candidate_table_columns_and_related_panels_are_reachable_at_target_heights() -> None:
    """Headers, unavailable values, selection, explanation, and comparison stay inspectable."""
    app = QApplication.instance() or QApplication([])
    window, _session = _window_with_rows()
    scroll = window.findChild(QScrollArea, "main-window-scroll-area")
    table = window.findChild(QTableWidget, "candidate-table")
    explanation = window.findChild(QTextEdit, "recommendation-explanation")
    comparison = window.findChild(QWidget, "candidate-comparison")
    add_comparison = window.findChild(QPushButton, "add-candidate-comparison")
    assert (
        scroll is not None
        and table is not None
        and explanation is not None
        and comparison is not None
        and add_comparison is not None
    )

    for height in (664, 900):
        window.resize(2559, height)
        window.show()
        app.processEvents()
        assert table.horizontalHeader().sectionSize(1) >= 148
        assert table.horizontalHeader().sectionSize(2) >= 112
        assert table.horizontalHeaderItem(3) is not None
        assert "unavailable" in table.horizontalHeaderItem(3).toolTip()
        assert table.horizontalHeaderItem(6) is not None
        assert "role-unknown" in table.horizontalHeaderItem(6).toolTip()
        assert table.item(0, 3) is not None and table.item(0, 3).text() == "—"
        assert table.item(0, 6) is not None and table.item(0, 6).text() == "—"

        _scroll_to_control(scroll, table)
        header_rect = QRect(
            table.horizontalHeader().mapToGlobal(QPoint(0, 0)), table.horizontalHeader().size()
        )
        first_item = table.item(0, 0)
        assert first_item is not None
        first_rect = table.visualItemRect(first_item)
        first_global = QRect(table.viewport().mapToGlobal(first_rect.topLeft()), first_rect.size())
        assert not header_rect.intersects(first_global)

        table.selectRow(1)
        selected_item = table.item(1, 0)
        assert (
            selected_item is not None
            and table.selectionBehavior() == table.SelectionBehavior.SelectRows
        )
        assert selected_item.isSelected()
        _scroll_to_control(scroll, explanation)
        assert "Candidate: Hero 2" in explanation.toPlainText()
        _scroll_to_control(scroll, comparison)
        _scroll_to_control(scroll, add_comparison)
    window.close()


def test_candidate_keyboard_navigation_remains_local_presentation_only() -> None:
    """Focus, filter, sort, selection, and comparison must not touch draft or pair state."""
    app = QApplication.instance() or QApplication([])
    service = CountingPairService()
    window, session = _window_with_rows(service)
    before = session.to_draft_state()
    window.resize(2559, 664)
    window.show()
    app.processEvents()
    table = window.findChild(QTableWidget, "candidate-table")
    search = window.findChild(QLineEdit, "candidate-search")
    explanation = window.findChild(QTextEdit, "recommendation-explanation")
    add_comparison = window.findChild(QPushButton, "add-candidate-comparison")
    controller = window.pair_refresh_controller
    assert (
        table is not None
        and search is not None
        and explanation is not None
        and add_comparison is not None
        and controller is not None
    )

    table.setFocus()
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert search.hasFocus()
    QTest.keyClicks(search, "hero")
    QTest.keyClick(search, Qt.Key.Key_Return)
    app.processEvents()
    assert table.hasFocus() and table.currentRow() == 0
    QTest.keyClick(table, Qt.Key.Key_Down)
    app.processEvents()
    assert table.currentRow() == 1
    assert "Candidate: Hero 2" in explanation.toPlainText()
    table.horizontalHeader().sectionClicked.emit(1)
    add_comparison.click()
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(search, Qt.Key.Key_Escape)
    app.processEvents()

    assert search.text() == "" and search.hasFocus()
    assert session.to_draft_state() == before
    assert service.calls == 0 and controller.generation == 0 and controller.active_thread is None
    assert window.findChildren(QThread) == []
    window.close()
